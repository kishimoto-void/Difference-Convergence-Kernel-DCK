# DCK v0.9 Demo Run Results

実行日時: 2026-07-29  
実行環境: Python 3.12 + pydantic / numpy / scipy  
実行コマンド: `PYTHONPATH=. python -m examples.basic_usage`

---

## 実行ログ

```text
=== DCK basic usage demo (stubs) ===
Initial resources: rev=ReversibleResource(compute_cpu=100.0, compute_gpu=4.0, bandwidth=10.0) irr=IrreversibleResource(capital_money=5000.0, energy_power=20.0, time_window=3600.0)

[turn 1] telemetry={'temperature': 29.2}
  event=EVT_intent_temperature_t... stage=EXECUTED gap=2.090 vel=0.000 action=ActionType.EXECUTE_CONVERGENCE

[turn 2] telemetry={'temperature': 28.4}

[turn 3] telemetry={'temperature': 27.6}

[turn 4] telemetry={'temperature': 26.8}

[turn 5] telemetry={'temperature': 26.0}

=== Snapshot ===
turn=5  version=v0.9
remaining resources: rev=ReversibleResource(compute_cpu=100.0, compute_gpu=4.0, bandwidth=10.0) irr=IrreversibleResource(capital_money=4997.909768752825, energy_power=20.0, time_window=3600.0)
active events: 1
intent records: 1
```

---

## 結果の解釈

| 項目 | 内容 |
|------|------|
| 起動 | KernelBuilder + StubObserver / StubPredictor / StubExecutor で正常起動 |
| turn 1 | gap ≈ 2.09 → DecisionEngine が `EXECUTE_CONVERGENCE` を選択し、Lease 予約 → 実行 → Commit 成功 |
| フィードバック | `process_delayed_feedback(actual=25.5)` により Intent が CONVERGED 扱いとなり完了マーク |
| turn 2〜5 | Intent 完了済みのため `get_runnable()` が空 → イベント生成なし（想定動作） |
| リソース消費 | 不可逆リソース `capital_money` が gap に応じて約 2.09 消費（5000 → 4997.91） |
| スナップショット | turn / resources / events / intents を Point-in-Time で取得成功 |

---

## 確認できた主要機能

- Intent 登録とスケジューリング
- Observer → Predictor → TransitionEvent 生成
- NormalizedPotentialEngine による意思決定
- 2-Phase Lease（Reserve → Commit）
- 遅延フィードバックによる Intent 完了
- 決定論的クロック（StepTimeProvider）と ID 生成
- スナップショットの一貫性取得

エラーなく閉ループが一通り動作することを確認しました。
