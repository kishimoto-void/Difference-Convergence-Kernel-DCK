"""Experiment 1: Capsuleなし vs Capsuleあり（LLM proxy）

条件:
  A: LLM → DCK          （Capsuleなし。生の状態を直接DCKへ）
  B: LLM → Capsule → DCK （Capsuleが維持すべき状態で探索空間を制約）

本実験は実LLM APIを呼ばず、既存のDCK + 最小Capsuleスタブで
「Capsuleが差異をどう削減するか」を定量的に観察するproxy実験です。

評価指標（proxy）:
  - token数相当     : 累積 gap × 定数（探索量の代理）
  - tool call数     : Executor 呼び出し回数
  - 修正回数        : EXECUTE_CONVERGENCE 回数
  - 最終品質        : 最終平均 gap（小さいほど良い）
  - 推論時間        : 壁時計時間（参考）

実行:
  PYTHONPATH=. python -m examples.experiment1_capsule_llm_proxy
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any

from dck import (
    KernelBuilder, DCKConfig, ResourceVector,
    ReversibleResource, IrreversibleResource, Intent, MetricGoal,
)
from dck.stubs import StubObserver, StubPredictor, StubExecutor
from dck.utils import StepTimeProvider
from dck.events import TransitionEvent


CONVERSATION = [
    {"turn": 1, "raw": {"topic_alignment": 0.85, "user_clarity": 0.90, "response_risk": 0.10}},
    {"turn": 2, "raw": {"topic_alignment": 0.78, "user_clarity": 0.75, "response_risk": 0.25}},
    {"turn": 3, "raw": {"topic_alignment": 0.45, "user_clarity": 0.60, "response_risk": 0.55}},
    {"turn": 4, "raw": {"topic_alignment": 0.82, "user_clarity": 0.88, "response_risk": 0.18}},
    {"turn": 5, "raw": {"topic_alignment": 0.91, "user_clarity": 0.92, "response_risk": 0.08}},
]


class SimplePLP:
    def __init__(self):
        self.history: List[Dict[str, float]] = []

    def process(self, raw: Dict[str, float]) -> Dict[str, float]:
        self.history.append(raw)
        window = self.history[-3:]
        smoothed = {}
        for k in ["topic_alignment", "user_clarity", "response_risk"]:
            vals = [d.get(k, 0.5) for d in window]
            avg = sum(vals) / len(vals)
            if k == "topic_alignment" and avg < 0.65:
                avg = 0.65 + (avg - 0.65) * 0.35
            if k == "response_risk" and avg > 0.35:
                avg = 0.35 + (avg - 0.35) * 0.35
            smoothed[k] = avg
        return smoothed


class SimpleCapsule:
    """維持すべき状態への拘束。探索空間を削る。"""
    def __init__(self, pull: float = 0.60):
        self.desired = {"topic_alignment": 0.90, "response_risk": 0.10}
        self.pull = pull

    def maintain(self, state: Dict[str, float]) -> Dict[str, float]:
        pulled = {}
        for k, des in self.desired.items():
            cur = state.get(k, des)
            pulled[k] = cur * (1.0 - self.pull) + des * self.pull
        if "user_clarity" in state:
            pulled["user_clarity"] = state["user_clarity"]
        return pulled


@dataclass
class ExpResult:
    condition: str
    events: List[TransitionEvent] = field(default_factory=list)
    total_gap: float = 0.0
    exec_count: int = 0
    executor_calls: int = 0
    final_capital: float = 0.0
    wall_time_sec: float = 0.0
    gaps_per_turn: List[float] = field(default_factory=list)

    @property
    def avg_gap(self) -> float:
        return self.total_gap / len(self.events) if self.events else 0.0

    @property
    def token_proxy(self) -> float:
        # 探索量の代理指標（gap累積をスケール）
        return self.total_gap * 120.0


async def run_exp(name: str, use_capsule: bool) -> ExpResult:
    result = ExpResult(condition=name)
    t0 = time.perf_counter()

    initial = ResourceVector(
        rev=ReversibleResource(compute_cpu=50.0, compute_gpu=2.0, bandwidth=5.0),
        irr=IrreversibleResource(capital_money=1000.0, energy_power=10.0, time_window=1800.0),
    )
    clock = StepTimeProvider(
        start_time=datetime(2026, 7, 29, 23, 0, 0, tzinfo=timezone.utc),
        step_seconds=1.5,
    )
    config = DCKConfig(
        max_gap_scale=1.0, max_risk_scale=1.0, target_velocity_scale=0.5,
        risk_safety_margin=1.5, weight_equivalence=1.2, weight_velocity=1.0,
        weight_congruence=0.3, weight_risk=1.5, convergence_tolerance=0.15,
        max_concurrency_execution=2,
    )
    executor = StubExecutor(always_succeed=True)

    kernel = (
        KernelBuilder(initial_resources=initial)
        .with_config(config)
        .with_capabilities(observer=StubObserver(), predictor=StubPredictor(), executor=executor)
        .with_clock(clock)
        .with_kernel_id(f"exp1_{name}")
        .build()
    )

    intent = Intent(
        intent_id="intent_conv_stability",
        description="会話安定性",
        goals={
            "topic_alignment": MetricGoal(target_value=0.90, tolerance=0.10),
            "response_risk": MetricGoal(target_value=0.10, tolerance=0.10),
        },
        time_horizon=3, created_turn=0, base_priority=3.0, deadline_turn=10,
    )
    kernel.scheduler.submit(intent)

    plp = SimplePLP()
    capsule = SimpleCapsule(pull=0.60) if use_capsule else None

    for item in CONVERSATION:
        raw = item["raw"]
        state = plp.process(raw)
        if capsule:
            telemetry = capsule.maintain(state)
        else:
            telemetry = state   # Capsuleなし = 生に近い状態をDCKへ

        events = await kernel.tick(current_turn=item["turn"], raw_telemetry=telemetry)

        turn_gap = 0.0
        for ev in events:
            result.events.append(ev)
            g = ev.compute_equivalence_gap()
            result.total_gap += g
            turn_gap += g
            if ev.decision_action and ev.decision_action.value == "EXECUTE_CONVERGENCE":
                result.exec_count += 1
            if ev.current_stage.value == "EXECUTED" and ev.lease_id:
                actual = 0.72 if ev.metric_name == "topic_alignment" else 0.28
                await kernel.process_delayed_feedback(ev.event_id, actual_value=actual)
        result.gaps_per_turn.append(turn_gap)

    snap = await kernel.take_snapshot()
    result.final_capital = snap.system_resources.irr.capital_money
    result.executor_calls = executor.call_count
    result.wall_time_sec = time.perf_counter() - t0
    return result


async def main():
    print("Experiment 1: Capsule なし vs あり (LLM proxy)")
    print("-" * 60)
    a = await run_exp("A_LLM_DCK", use_capsule=False)
    b = await run_exp("B_LLM_Capsule_DCK", use_capsule=True)

    print(f"{'Metric':<22} {'A (no Capsule)':>16} {'B (with Capsule)':>18} {'Δ':>10}")
    print("-" * 70)
    print(f"{'token_proxy':<22} {a.token_proxy:>16.1f} {b.token_proxy:>18.1f} {b.token_proxy - a.token_proxy:>+10.1f}")
    print(f"{'tool_call (executor)':<22} {a.executor_calls:>16} {b.executor_calls:>18} {b.executor_calls - a.executor_calls:>+10}")
    print(f"{'correction (EXEC)':<22} {a.exec_count:>16} {b.exec_count:>18} {b.exec_count - a.exec_count:>+10}")
    print(f"{'final_quality (avg gap)':<22} {a.avg_gap:>16.3f} {b.avg_gap:>18.3f} {b.avg_gap - a.avg_gap:>+10.3f}")
    print(f"{'wall_time_sec':<22} {a.wall_time_sec:>16.3f} {b.wall_time_sec:>18.3f} {b.wall_time_sec - a.wall_time_sec:>+10.3f}")
    print(f"{'T3_gap (max drift)':<22} {a.gaps_per_turn[2]:>16.3f} {b.gaps_per_turn[2]:>18.3f} {b.gaps_per_turn[2] - a.gaps_per_turn[2]:>+10.3f}")
    print(f"{'capital_remaining':<22} {a.final_capital:>16.2f} {b.final_capital:>18.2f} {b.final_capital - a.final_capital:>+10.2f}")
    print("-" * 70)
    print("※ token_proxy / quality は gap ベースの代理指標（実LLM未使用）")
    return a, b


if __name__ == "__main__":
    asyncio.run(main())
