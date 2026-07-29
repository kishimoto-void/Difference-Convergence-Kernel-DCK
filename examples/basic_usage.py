"""DCK v0.9 基本利用例（スタブ使用）

実行方法:
    python -m examples.basic_usage

依存: pydantic, numpy, scipy
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone

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


async def main() -> None:
    # 初期リソース
    initial = ResourceVector(
        rev=ReversibleResource(compute_cpu=100.0, compute_gpu=4.0, bandwidth=10.0),
        irr=IrreversibleResource(capital_money=5000.0, energy_power=20.0, time_window=3600.0),
    )

    # 決定論的クロック（テスト再現性）
    clock = StepTimeProvider(
        start_time=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
        step_seconds=1.0,
    )

    # Kernel 構築
    kernel = (
        KernelBuilder(initial_resources=initial)
        .with_config(DCKConfig(max_concurrency_execution=4))
        .with_capabilities(
            observer=StubObserver(),
            predictor=StubPredictor(drift=0.0),
            executor=StubExecutor(always_succeed=True),
        )
        .with_clock(clock)
        .with_kernel_id("dck_demo_01")
        .build()
    )

    # Intent 登録
    intent = Intent(
        intent_id="intent_temperature",
        description="温度を目標値へ収束させる",
        goals={
            "temperature": MetricGoal(target_value=25.0, tolerance=1.0),
        },
        time_horizon=5,
        created_turn=0,
        base_priority=2.0,
        deadline_turn=20,
    )
    kernel.scheduler.submit(intent)

    print("=== DCK basic usage demo (stubs) ===")
    print(f"Initial resources: {kernel.system_resources}")
    print()

    # 数ターン実行
    for turn in range(1, 6):
        # 擬似テレメトリ（徐々に目標へ近づく）
        telemetry = {"temperature": 30.0 - turn * 0.8}
        events = await kernel.tick(current_turn=turn, raw_telemetry=telemetry)

        print(f"[turn {turn}] telemetry={telemetry}")
        for ev in events:
            print(
                f"  event={ev.event_id[:24]}... "
                f"stage={ev.current_stage.value} "
                f"gap={ev.compute_equivalence_gap():.3f} "
                f"vel={ev.computed_velocity:.3f} "
                f"action={ev.decision_action}"
            )

        # 簡易フィードバック（EXECUTED なら即 CONVERGED 扱いに近づける）
        for ev in events:
            if ev.current_stage.value == "EXECUTED" and ev.lease_id:
                # 実際の値が目標に近づいたと仮定
                await kernel.process_delayed_feedback(ev.event_id, actual_value=25.5)

        print()

    # スナップショット取得
    snap = await kernel.take_snapshot()
    print("=== Snapshot ===")
    print(f"turn={snap.turn}  version={snap.snapshot_version}")
    print(f"remaining resources: {snap.system_resources}")
    print(f"active events: {len(snap.active_events)}")
    print(f"intent records: {len(snap.intent_records)}")


if __name__ == "__main__":
    asyncio.run(main())
