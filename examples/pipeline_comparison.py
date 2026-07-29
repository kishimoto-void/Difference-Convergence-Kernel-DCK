"""DCK Pipeline Comparison Experiment

条件比較:
  A. DCK only               (生テレメトリを直接流す)
  B. PSS → DCK              (PSSが問題を構造化)
  C. PLP + Capsule → DCK    (Capsuleが「維持すべき状態」を供給し探索空間を削る)
  D. Full pipeline          (PSS → PLP → Capsule → DCK)

同じ日常会話シナリオを使い、
イベント数・平均gap・Action分布・リソース消費を比較する。

実行:
  PYTHONPATH=. python -m examples.pipeline_comparison
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from dck import (
    KernelBuilder,
    DCKConfig,
    ResourceVector,
    ReversibleResource,
    IrreversibleResource,
    Intent,
    MetricGoal,
)
from dck.stubs import StubObserver, StubPredictor, StubExecutor
from dck.utils import StepTimeProvider
from dck.events import TransitionEvent


# ============================================================
# 共通会話シナリオ（全条件で同一入力）
# ============================================================
CONVERSATION = [
    {"turn": 1, "user": "今日の姫路の天気どうかな？",
     "raw": {"topic_alignment": 0.85, "user_clarity": 0.90, "response_risk": 0.10}},
    {"turn": 2, "user": "あ、あと夕方から雨っぽいかもって聞いたんだけど",
     "raw": {"topic_alignment": 0.78, "user_clarity": 0.75, "response_risk": 0.25}},
    {"turn": 3, "user": "ちなみに明日の朝は？ あと週末の予定も聞きたいんだけど",
     "raw": {"topic_alignment": 0.45, "user_clarity": 0.60, "response_risk": 0.55}},
    {"turn": 4, "user": "いや、天気の話だけでいいよ。週末はまた今度で",
     "raw": {"topic_alignment": 0.82, "user_clarity": 0.88, "response_risk": 0.18}},
    {"turn": 5, "user": "ありがとう。予報信頼できそう？",
     "raw": {"topic_alignment": 0.91, "user_clarity": 0.92, "response_risk": 0.08}},
]


# ============================================================
# 役割を持たせた最小スタブ
# ============================================================
class SimplePSS:
    """PSS: 生の状態を「解くべき問題」として構造化する。
    ここでは大きな逸脱を問題として強調する。
    """
    def specify(self, raw: Dict[str, float]) -> Dict[str, Any]:
        ta = raw.get("topic_alignment", 0.5)
        rr = raw.get("response_risk", 0.5)
        return {
            "raw": {
                "topic_alignment": ta,
                "user_clarity": raw.get("user_clarity", 0.8),
                "response_risk": rr,
            },
            "source": "pss",
        }


class SimplePLP:
    """PLP: 履歴を持ち急激な変化を平滑化する。
    一時的なノイズをDCKに伝えないようにする。
    """
    def __init__(self):
        self.history: List[Dict[str, float]] = []

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        current = data.get("raw", data)
        self.history.append(current)
        window = self.history[-3:]
        smoothed = {}
        for k in ["topic_alignment", "user_clarity", "response_risk"]:
            vals = [d.get(k, 0.5) for d in window]
            avg = sum(vals) / len(vals)
            # 大きな逸脱を減衰（特にTurn3）
            if k == "topic_alignment" and avg < 0.65:
                avg = 0.65 + (avg - 0.65) * 0.35
            if k == "response_risk" and avg > 0.35:
                avg = 0.35 + (avg - 0.35) * 0.35
            smoothed[k] = avg
        return {"smoothed": smoothed, "raw": current, "source": "plp"}


class SimpleCapsule:
    """Capsule: 「維持すべき状態」を保持し、観測値を desired 方向へ引き寄せる。
    これによりDCKが扱う差異（探索空間）が小さくなる。
    """
    def __init__(self):
        self.desired = {"topic_alignment": 0.90, "response_risk": 0.10}
        self.pull = 0.60   # 拘束の強さ

    def maintain(self, data: Dict[str, Any]) -> Dict[str, float]:
        base = data.get("smoothed", data.get("raw", {}))
        pulled = {}
        for k, des in self.desired.items():
            cur = base.get(k, des)
            pulled[k] = cur * (1.0 - self.pull) + des * self.pull
        if "user_clarity" in base:
            pulled["user_clarity"] = base["user_clarity"]
        return pulled


# ============================================================
# 結果記録
# ============================================================
@dataclass
class RunResult:
    condition: str
    events: List[TransitionEvent] = field(default_factory=list)
    action_counts: Dict[str, int] = field(default_factory=lambda: {
        "NO_ACTION": 0, "EXECUTE_CONVERGENCE": 0, "SAFETY_HALT": 0
    })
    total_gap: float = 0.0
    gaps_per_turn: List[float] = field(default_factory=list)
    final_capital: float = 0.0
    intent_completed: bool = False
    executor_calls: int = 0


async def run_condition(name: str, use_pss: bool, use_plp: bool, use_capsule: bool) -> RunResult:
    result = RunResult(condition=name)

    initial = ResourceVector(
        rev=ReversibleResource(compute_cpu=50.0, compute_gpu=2.0, bandwidth=5.0),
        irr=IrreversibleResource(capital_money=1000.0, energy_power=10.0, time_window=1800.0),
    )
    clock = StepTimeProvider(
        start_time=datetime(2026, 7, 29, 21, 30, 0, tzinfo=timezone.utc),
        step_seconds=2.0,
    )
    config = DCKConfig(
        max_gap_scale=1.0,
        max_risk_scale=1.0,
        target_velocity_scale=0.5,
        risk_safety_margin=1.5,
        weight_equivalence=1.2,
        weight_velocity=1.0,
        weight_congruence=0.3,
        weight_risk=1.5,
        convergence_tolerance=0.15,
        max_concurrency_execution=2,
    )
    executor = StubExecutor(always_succeed=True)

    kernel = (
        KernelBuilder(initial_resources=initial)
        .with_config(config)
        .with_capabilities(
            observer=StubObserver(),
            predictor=StubPredictor(drift=0.0),
            executor=executor,
        )
        .with_clock(clock)
        .with_kernel_id(f"dck_{name}")
        .build()
    )

    intent = Intent(
        intent_id="intent_conversation_stability",
        description="会話安定性の維持",
        goals={
            "topic_alignment": MetricGoal(target_value=0.90, tolerance=0.10),
            "response_risk": MetricGoal(target_value=0.10, tolerance=0.10),
        },
        time_horizon=3,
        created_turn=0,
        base_priority=3.0,
        deadline_turn=10,
    )
    kernel.scheduler.submit(intent)

    pss = SimplePSS() if use_pss else None
    plp = SimplePLP() if use_plp else None
    capsule = SimpleCapsule() if use_capsule else None

    for item in CONVERSATION:
        turn = item["turn"]
        raw = item["raw"]

        # パイプライン
        data: Dict[str, Any] = {"raw": raw}
        if pss:
            data = pss.specify(raw)
        if plp:
            data = plp.process(data)
        if capsule:
            telemetry = capsule.maintain(data)
        else:
            telemetry = data.get("smoothed", data.get("raw", raw))

        events = await kernel.tick(current_turn=turn, raw_telemetry=telemetry)

        turn_gap = 0.0
        for ev in events:
            result.events.append(ev)
            g = ev.compute_equivalence_gap()
            result.total_gap += g
            turn_gap += g
            action_str = ev.decision_action.value if ev.decision_action else "None"
            if action_str in result.action_counts:
                result.action_counts[action_str] += 1

            if ev.current_stage.value == "EXECUTED" and ev.lease_id:
                actual = 0.72 if ev.metric_name == "topic_alignment" else 0.28
                await kernel.process_delayed_feedback(ev.event_id, actual_value=actual)

        result.gaps_per_turn.append(turn_gap)

    snap = await kernel.take_snapshot()
    result.final_capital = snap.system_resources.irr.capital_money
    result.intent_completed = list(snap.intent_records.values())[0].is_completed if snap.intent_records else False
    result.executor_calls = executor.call_count
    return result


async def main():
    print("Running 4 conditions (PSS / PLP / Capsule / DCK)...")
    results = [
        await run_condition("A_DCK_only",           use_pss=False, use_plp=False, use_capsule=False),
        await run_condition("B_PSS_DCK",             use_pss=True,  use_plp=False, use_capsule=False),
        await run_condition("C_PLP_Capsule_DCK",     use_pss=False, use_plp=True,  use_capsule=True),
        await run_condition("D_Full_PSS_PLP_Cap_DCK",use_pss=True,  use_plp=True,  use_capsule=True),
    ]

    print("\n" + "=" * 88)
    print("COMPARISON SUMMARY")
    print("=" * 88)
    header = f"{'Condition':<28} {'Events':>7} {'EXEC':>5} {'AvgGap':>8} {'T3_Gap':>8} {'Capital':>9} {'Calls':>6}"
    print(header)
    print("-" * 88)
    for r in results:
        n = len(r.events)
        exec_c = r.action_counts["EXECUTE_CONVERGENCE"]
        avg = r.total_gap / n if n else 0.0
        t3 = r.gaps_per_turn[2] if len(r.gaps_per_turn) > 2 else 0.0
        print(f"{r.condition:<28} {n:>7} {exec_c:>5} {avg:>8.3f} {t3:>8.3f} {r.final_capital:>9.2f} {r.executor_calls:>6}")

    print("\n(詳細レポートは experiments/pipeline_comparison_report.md に出力)")
    return results


if __name__ == "__main__":
    asyncio.run(main())
