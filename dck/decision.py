"""DCK Protocol 化された ResourceAllocator と Potential 決定エンジン"""
import math
from datetime import datetime
from typing import Protocol, Tuple, Optional
from pydantic import BaseModel, ConfigDict, Field
from dck.types import ActionType
from dck.resources import ResourceVector, ReversibleResource, IrreversibleResource
from dck.events import TransitionEvent
from dck.config import DCKConfig

class IResourceAllocator(Protocol):
    def allocate(
        self, event: TransitionEvent, action: ActionType, available: ResourceVector, config: DCKConfig
    ) -> ResourceVector: ...

class DefaultResourceAllocator:
    def allocate(
        self, event: TransitionEvent, action: ActionType, available: ResourceVector, config: DCKConfig
    ) -> ResourceVector:
        if action in (ActionType.NO_ACTION, ActionType.SAFETY_HALT):
            return ResourceVector()
        
        raw_gap = event.compute_equivalence_gap()
        return ResourceVector(
            rev=ReversibleResource(compute_cpu=min(available.rev.compute_cpu, raw_gap * 0.5)),
            irr=IrreversibleResource(capital_money=min(available.irr.capital_money, raw_gap * 1.0))
        )

class DecisionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, strict=True, extra="forbid")

    event: TransitionEvent
    available_resources: ResourceVector
    priority: float
    deadline_turn: Optional[int]
    current_turn: int
    gap_history: Tuple[Tuple[datetime, float], ...] = Field(default_factory=tuple)

class DecisionEngine(Protocol):
    async def decide(self, ctx: DecisionContext, config: DCKConfig) -> ActionType: ...

class NormalizedPotentialEngine:
    @staticmethod
    def _softplus(x: float, k: float) -> float:
        return (1.0 / k) * math.log1p(math.exp(k * x))

    async def decide(self, ctx: DecisionContext, config: DCKConfig) -> ActionType:
        evt = ctx.event
        
        raw_gap = evt.compute_equivalence_gap()
        raw_velocity = evt.computed_velocity
        raw_risk = evt.compute_risk_score(config.min_uncertainty)

        norm_gap = min(1.0, raw_gap / config.max_gap_scale)
        norm_risk = min(1.0, raw_risk / config.max_risk_scale)
        norm_velocity = raw_velocity / config.target_velocity_scale

        if norm_gap + config.risk_safety_margin * norm_risk > 1.5 and norm_risk > 0.8:
            return ActionType.SAFETY_HALT

        if norm_gap < 0.001:
            return ActionType.NO_ACTION

        dummy_alloc = ResourceVector(
            rev=ReversibleResource(compute_cpu=min(ctx.available_resources.rev.compute_cpu, raw_gap * 0.5))
        )

        norm_congruence = ctx.available_resources.congruence_index(dummy_alloc)
        smooth_neg_velocity = self._softplus(-norm_velocity, k=config.softplus_k)
        
        phi_potential = (
            config.weight_equivalence * norm_gap +
            config.weight_velocity * smooth_neg_velocity +
            config.weight_congruence / (norm_congruence + 1e-5) +
            config.weight_risk * norm_risk
        )

        if phi_potential > 0.05 or ctx.priority > 5.0:
            return ActionType.EXECUTE_CONVERGENCE

        return ActionType.NO_ACTION
