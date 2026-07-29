"""DCK Kernel (DifferenceConvergenceKernel) 本体実装 (v0.9)"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Callable
from pydantic import BaseModel, ConfigDict

from dck.config import DCKConfig
from dck.types import ActionType, TransitionStage, StateEstimate
from dck.resources import ResourceVector, LeaseManager
from dck.events import TransitionEvent, TwoTierEventCache, KernelSnapshot
from dck.intents import IntentScheduler, IntentRecord, MetricGoal
from dck.observation import IObserverCapability, IPredictorCapability, IExecutorCapability, AbstractCompensationStrategy
from dck.decision import DecisionEngine, IResourceAllocator, DecisionContext
from dck.utils import DeterministicIDGenerator, GapHistory

class KernelContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")
    turn: int
    now: datetime
    runnable_records: Tuple[IntentRecord, ...]
    estimated_states: Dict[str, StateEstimate]

class DifferenceConvergenceKernel:
    def __init__(
        self,
        system_resources: ResourceVector,
        observer: IObserverCapability,
        predictor: IPredictorCapability,
        executor: IExecutorCapability,
        resource_allocator: IResourceAllocator,
        compensation_strategy: AbstractCompensationStrategy,
        config: DCKConfig,
        decision_engine: DecisionEngine,
        time_provider: Callable[[], datetime],
        kernel_id: str = "dck_k01",
        logger_instance: Optional[logging.Logger] = None
    ):
        self.config = config
        self.turn = 0
        self.kernel_id = kernel_id
        self.lease_manager = LeaseManager(system_resources)
        self.scheduler = IntentScheduler(self.config)
        self.observer = observer
        self.predictor = predictor
        self.executor = executor
        self.resource_allocator = resource_allocator
        self.compensation_strategy = compensation_strategy
        self.decision_engine = decision_engine
        
        self.get_time = time_provider
        self.gen_id = DeterministicIDGenerator(kernel_id=self.kernel_id)
        self.logger = logger_instance or logging.getLogger("DCK")

        self.event_cache = TwoTierEventCache(
            active_capacity=self.config.active_cache_capacity,
            archive_capacity=self.config.archive_cache_capacity
        )
        self.gap_histories: Dict[str, GapHistory] = {}
        self._last_tick_time: Optional[datetime] = None
        
        self._execution_semaphore = asyncio.Semaphore(self.config.max_concurrency_execution)
        self._state_lock = asyncio.Lock()

    @property
    def system_resources(self) -> ResourceVector:
        return self.lease_manager.current_resources

    async def tick(self, current_turn: int, raw_telemetry: Dict[str, Any]) -> List[TransitionEvent]:
        async with self._state_lock:
            self.turn = current_turn
            now = self.get_time()
            self._last_tick_time = now

            k_ctx = await self._observe_and_predict(current_turn, now, raw_telemetry)
            if not k_ctx or not k_ctx.runnable_records:
                return []

            self.scheduler.mark_active([r.intent.intent_id for r in k_ctx.runnable_records])
            events_to_process = await self._evaluate_events(k_ctx)
        
        processed_events = await self._execute_transactions_parallel(k_ctx, events_to_process)
        return processed_events

    async def _observe_and_predict(
        self, current_turn: int, now: datetime, raw_telemetry: Dict[str, Any]
    ) -> Optional[KernelContext]:
        runnable = self.scheduler.get_runnable(current_turn)
        if not runnable:
            return None

        try:
            estimated_states = await asyncio.wait_for(
                self.observer.observe(raw_telemetry),
                timeout=self.config.transaction_timeout_sec
            )
        except asyncio.TimeoutError:
            self.logger.error("Observer timeout", extra={"turn": current_turn, "kernel_id": self.kernel_id})
            return None

        return KernelContext(
            turn=current_turn,
            now=now,
            runnable_records=tuple(runnable),
            estimated_states=estimated_states
        )

    async def _evaluate_events(self, k_ctx: KernelContext) -> List[TransitionEvent]:
        forecast_requests: List[Tuple[IntentRecord, str, StateEstimate, MetricGoal]] = []
        for rec in k_ctx.runnable_records:
            intent = rec.intent
            for m_name, goal in intent.goals.items():
                if m_name in k_ctx.estimated_states:
                    obs_est = k_ctx.estimated_states[m_name]
                    forecast_requests.append((rec, m_name, obs_est, goal))

        if not forecast_requests:
            return []

        tasks = [
            self.predictor.forecast(m_name, obs_est, rec.intent.time_horizon)
            for rec, m_name, obs_est, _ in forecast_requests
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        events = []
        for (rec, m_name, obs_est, goal), proj_res in zip(forecast_requests, results):
            if isinstance(proj_res, Exception):
                self.logger.error(
                    "Predictor execution failed",
                    extra={"metric": m_name, "error": str(proj_res)}
                )
                continue

            proj_est: StateEstimate = proj_res
            intent = rec.intent
            history_key = f"{intent.intent_id}_{m_name}"
            if history_key not in self.gap_histories:
                self.gap_histories[history_key] = GapHistory(
                    maxlen=self.config.gap_history_size,
                    tau=self.config.velocity_time_constant_tau
                )

            event_id = self.gen_id(f"EVT_{intent.intent_id}_{m_name}")
            
            temp_event = TransitionEvent(
                event_id=event_id,
                intent_id=intent.intent_id,
                metric_name=m_name,
                expected_state=goal.target_value,
                observed_state=obs_est,
                projected_state=proj_est,
                created_turn=k_ctx.turn,
                created_at=k_ctx.now,
                current_stage=TransitionStage.PROJECTED
            )

            smoothed_v = self.gap_histories[history_key].push(k_ctx.now, temp_event.compute_equivalence_gap())
            event = temp_event.model_copy(update={"computed_velocity": smoothed_v})

            events.append(event)
            self.event_cache.put(event)

        return events

    async def _execute_single_event(self, k_ctx: KernelContext, event: TransitionEvent) -> TransitionEvent:
        async with self._execution_semaphore:
            rec = self.scheduler.get_record(event.intent_id)
            if not rec:
                return event

            intent = rec.intent
            d_ctx = DecisionContext(
                event=event,
                available_resources=self.lease_manager.current_resources,
                priority=intent.effective_priority(k_ctx.turn, self.config),
                deadline_turn=intent.deadline_turn,
                current_turn=k_ctx.turn,
                gap_history=tuple(self.gap_histories[f"{intent.intent_id}_{event.metric_name}"].history)
            )

            action = await self.decision_engine.decide(d_ctx, self.config)
            if action == ActionType.NO_ACTION:
                return event

            if action == ActionType.SAFETY_HALT:
                updated_evt = event.with_stage(TransitionStage.FAILED, decision_action=action)
                self.event_cache.put(updated_evt)
                self.logger.warning("Safety halt executed", extra={"event_id": event.event_id, "intent_id": event.intent_id})
                return updated_evt

            alloc = self.resource_allocator.allocate(event, action, self.lease_manager.current_resources, self.config)

            lease_id = self.gen_id(f"LEASE_{event.event_id}")
            reservation = await self.lease_manager.reserve_reversible(lease_id, event.event_id, alloc, k_ctx.now)
            if not reservation:
                updated_evt = event.with_stage(TransitionStage.FAILED, decision_action=action)
                self.event_cache.put(updated_evt)
                return updated_evt

            working_evt = event.model_copy(update={"lease_id": lease_id, "decision_action": action})

            async with reservation:
                try:
                    success = await asyncio.wait_for(
                        self.executor.execute(action, alloc),
                        timeout=self.config.transaction_timeout_sec
                    )
                    if success and await reservation.commit_irreversible():
                        final_evt = working_evt.with_stage(TransitionStage.EXECUTED)
                    else:
                        final_evt = working_evt.with_stage(TransitionStage.FAILED)
                except Exception as e:
                    self.logger.exception("Execution failed", extra={"event_id": event.event_id, "error": str(e)})
                    final_evt = working_evt.with_stage(TransitionStage.FAILED)

            self.event_cache.put(final_evt)
            return final_evt

    async def _execute_transactions_parallel(
        self, k_ctx: KernelContext, events: List[TransitionEvent]
    ) -> List[TransitionEvent]:
        tasks = [self._execute_single_event(k_ctx, evt) for evt in events]
        return list(await asyncio.gather(*tasks))

    async def process_delayed_feedback(self, event_id: str, actual_value: float) -> None:
        async with self._state_lock:
            event = self.event_cache.get(event_id)
            if not event:
                return

            if abs(actual_value - event.expected_state) <= self.config.convergence_tolerance:
                final_stage = TransitionStage.CONVERGED
                self.scheduler.mark_completed(event.intent_id)
            else:
                final_stage = TransitionStage.FAILED
                if event.lease_id:
                    alloc = self.lease_manager.get_lease_reserved_resource(event.lease_id) or ResourceVector()
                    await self.compensation_strategy.compensate(event, alloc)

            if event.lease_id:
                await self.lease_manager.release(event.lease_id)

            updated_event = event.with_stage(final_stage, actual_state=actual_value)
            self.event_cache.put(updated_event)

    async def take_snapshot(self) -> KernelSnapshot:
        """DCK 二重階層ロックによる Point-in-Time スナップショット保証 (v0.9)"""
        async with self._state_lock:
            async with self.lease_manager.lock:
                snapshot_time = self._last_tick_time or self.get_time()
                return KernelSnapshot(
                    turn=self.turn,
                    system_resources=self.lease_manager.current_resources.model_copy(),
                    intent_records=self.scheduler.get_all_records(),
                    active_events=self.event_cache.all_events(),
                    active_leases=dict(self.lease_manager.get_all_leases()),
                    snapshot_version="v0.9",
                    timestamp=snapshot_time
                )
