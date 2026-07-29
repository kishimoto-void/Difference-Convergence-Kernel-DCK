"""DCK Conversation Convergence Demo (日常会話入力)

目的:
  日常会話をテレメトリとして扱い、
  「現在の会話状態」と「望ましい会話状態」の差異を
  DCK がどのように収束判断するかを観察する。

測るもの（簡易）:
  - 各ターンで DecisionEngine が選んだ Action
  - equivalence gap の推移
  - 実行された収束アクションの回数
  - 最終的な Intent 完了状況

実行:
  PYTHONPATH=. python -m examples.conversation_demo
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

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
from dck.types import ActionType


# -------------------------------------------------
# 日常会話シナリオ（テスト入力）
# 各要素は「その時点の会話状態を表す擬似スコア」
# -------------------------------------------------
CONVERSATION_TURNS = [
    {
        "turn": 1,
        "user": "今日の姫路の天気どうかな？",
        "telemetry": {
            "topic_alignment": 0.85,   # 目標トピックへの一致度 (高いほど良い)
            "user_clarity": 0.90,      # ユーザー発話の明確さ
            "response_risk": 0.10,     # 応答がズレるリスク
        },
    },
    {
        "turn": 2,
        "user": "あ、あと夕方から雨っぽいかもって聞いたんだけど",
        "telemetry": {
            "topic_alignment": 0.78,
            "user_clarity": 0.75,
            "response_risk": 0.25,
        },
    },
    {
        "turn": 3,
        "user": "ちなみに明日の朝は？ あと週末の予定も聞きたいんだけど",
        "telemetry": {
            "topic_alignment": 0.45,   # トピックが広がり始めた
            "user_clarity": 0.60,
            "response_risk": 0.55,     # リスク上昇
        },
    },
    {
        "turn": 4,
        "user": "いや、天気の話だけでいいよ。週末はまた今度で",
        "telemetry": {
            "topic_alignment": 0.82,   # ユーザーが軌道修正
            "user_clarity": 0.88,
            "response_risk": 0.18,
        },
    },
    {
        "turn": 5,
        "user": "ありがとう。予報信頼できそう？",
        "telemetry": {
            "topic_alignment": 0.91,
            "user_clarity": 0.92,
            "response_risk": 0.08,
        },
    },
]


async def main() -> None:
    initial = ResourceVector(
        rev=ReversibleResource(compute_cpu=50.0, compute_gpu=2.0, bandwidth=5.0),
        irr=IrreversibleResource(capital_money=1000.0, energy_power=10.0, time_window=1800.0),
    )

    clock = StepTimeProvider(
        start_time=datetime(2026, 7, 29, 21, 0, 0, tzinfo=timezone.utc),
        step_seconds=2.0,
    )

    # やや敏感な設定（小さな差異でも動きやすく）
    config = DCKConfig(
        max_gap_scale=1.0,          # 正規化を厳しめに
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
        .with_kernel_id("dck_conv_01")
        .build()
    )

    # 目標状態を Intent として登録
    # 「会話の topic_alignment を高く保つ」「response_risk を低く保つ」
    intent = Intent(
        intent_id="intent_conversation_stability",
        description="日常会話のトピック整合性と応答リスクを望ましい範囲に収束させる",
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

    print("=" * 60)
    print("DCK Conversation Convergence Demo")
    print("入力: 日常会話シナリオ（天気の話）")
    print("=" * 60)
    print()

    action_counts: Dict[str, int] = {
        "NO_ACTION": 0,
        "EXECUTE_CONVERGENCE": 0,
        "SAFETY_HALT": 0,
    }
    total_events = 0

    for item in CONVERSATION_TURNS:
        turn = item["turn"]
        user_text = item["user"]
        telemetry = item["telemetry"]

        print(f"[Turn {turn}] User: 「{user_text}」")
        print(f"  telemetry: {telemetry}")

        events = await kernel.tick(current_turn=turn, raw_telemetry=telemetry)
        total_events += len(events)

        if not events:
            print("  → イベントなし（Intent 完了 or runnable なし）")
        for ev in events:
            action_str = ev.decision_action.value if ev.decision_action else "None"
            if action_str in action_counts:
                action_counts[action_str] += 1

            print(
                f"  event={ev.metric_name:18s} "
                f"stage={ev.current_stage.value:10s} "
                f"gap={ev.compute_equivalence_gap():.3f} "
                f"vel={ev.computed_velocity:+.3f} "
                f"action={action_str}"
            )

            # 簡易フィードバック: 部分改善のみにして Intent を長く観察できるようにする
            # （実際の会話では一度の修正で完全収束しないイメージ）
            if ev.current_stage.value == "EXECUTED" and ev.lease_id:
                if ev.metric_name == "topic_alignment":
                    actual = 0.72   # 目標 0.90 からまだ遠い
                else:
                    actual = 0.28   # 目標 0.10 からまだ遠い
                await kernel.process_delayed_feedback(ev.event_id, actual_value=actual)

        print()

    # 最終スナップショット
    snap = await kernel.take_snapshot()
    print("=" * 60)
    print("最終 Snapshot")
    print(f"  turn              : {snap.turn}")
    print(f"  snapshot_version  : {snap.snapshot_version}")
    print(f"  remaining capital : {snap.system_resources.irr.capital_money:.2f}")
    print(f"  active events     : {len(snap.active_events)}")
    print(f"  intent completed  : {list(snap.intent_records.values())[0].is_completed if snap.intent_records else 'N/A'}")
    print()
    print("Action 集計")
    for k, v in action_counts.items():
        print(f"  {k:20s}: {v}")
    print(f"  total events generated : {total_events}")
    print(f"  executor call count    : {executor.call_count}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
