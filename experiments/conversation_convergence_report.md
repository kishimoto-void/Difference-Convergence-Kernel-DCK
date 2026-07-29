# DCK Conversation Convergence Experiment Report

**Date**: 2026-07-29  
**Version**: DCK v0.9  
**Script**: `examples/conversation_demo.py`  
**Input type**: Everyday conversation (姫路の天気に関する日常対話)

---

## 1. 実験の意図

PLP + PSS + Capsule + DCK の役割分担を本格的に測る前段階として、
**DCK 単体が「日常会話の状態差異」をどう扱うか**を観察した。

本実験では以下を確認する：

1. 会話状態をテレメトリとして扱ったとき、DCK が差異（gap）を正しく検出できるか
2. トピックが逸脱したときに gap / velocity がどう変化するか
3. ユーザー自身が軌道修正したときに velocity が正に転じるか
4. DecisionEngine が一貫して `EXECUTE_CONVERGENCE` を選択し続けるか（または NO_ACTION / SAFETY_HALT に切り替わるか）

---

## 2. 実験設定

### Intent（目標状態）

| Metric | Target | Tolerance |
|--------|--------|-----------|
| `topic_alignment` | 0.90 | 0.10 |
| `response_risk` | 0.10 | 0.10 |

### 日常会話シナリオ（5ターン）

| Turn | User utterance | topic_alignment | response_risk |
|------|----------------|-----------------|---------------|
| 1 | 今日の姫路の天気どうかな？ | 0.85 | 0.10 |
| 2 | あ、あと夕方から雨っぽいかもって聞いたんだけど | 0.78 | 0.25 |
| 3 | ちなみに明日の朝は？ あと週末の予定も聞きたいんだけど | **0.45** | **0.55** |
| 4 | いや、天気の話だけでいいよ。週末はまた今度で | 0.82 | 0.18 |
| 5 | ありがとう。予報信頼できそう？ | 0.91 | 0.08 |

Turn 3 で意図的にトピックを広げ、Turn 4 でユーザー自身が修正するシナリオ。

### フィードバック方針

完全収束させず、部分改善（actual = 0.72 / 0.28）を返すことで Intent を長く観察可能にした。

---

## 3. 実行結果（生ログ）

```text
============================================================
DCK Conversation Convergence Demo
入力: 日常会話シナリオ（天気の話）
============================================================

[Turn 1] User: 「今日の姫路の天気どうかな？」
  telemetry: {'topic_alignment': 0.85, 'user_clarity': 0.9, 'response_risk': 0.1}
  event=topic_alignment    stage=EXECUTED   gap=0.177 vel=+0.000 action=EXECUTE_CONVERGENCE
  event=response_risk      stage=EXECUTED   gap=0.011 vel=+0.000 action=EXECUTE_CONVERGENCE

[Turn 2] User: 「あ、あと夕方から雨っぽいかもって聞いたんだけど」
  telemetry: {'topic_alignment': 0.78, 'user_clarity': 0.75, 'response_risk': 0.25}
  event=topic_alignment    stage=EXECUTED   gap=0.293 vel=-0.036 action=EXECUTE_CONVERGENCE
  event=response_risk      stage=EXECUTED   gap=0.237 vel=-0.072 action=EXECUTE_CONVERGENCE

[Turn 3] User: 「ちなみに明日の朝は？ あと週末の予定も聞きたいんだけど」
  telemetry: {'topic_alignment': 0.45, 'user_clarity': 0.6, 'response_risk': 0.55}
  event=topic_alignment    stage=EXECUTED   gap=0.837 vel=-0.185 action=EXECUTE_CONVERGENCE
  event=response_risk      stage=EXECUTED   gap=0.731 vel=-0.183 action=EXECUTE_CONVERGENCE

[Turn 4] User: 「いや、天気の話だけでいいよ。週末はまた今度で」
  telemetry: {'topic_alignment': 0.82, 'user_clarity': 0.88, 'response_risk': 0.18}
  event=topic_alignment    stage=EXECUTED   gap=0.227 vel=+0.125 action=EXECUTE_CONVERGENCE
  event=response_risk      stage=EXECUTED   gap=0.121 vel=+0.126 action=EXECUTE_CONVERGENCE

[Turn 5] User: 「ありがとう。予報信頼できそう？」
  telemetry: {'topic_alignment': 0.91, 'user_clarity': 0.92, 'response_risk': 0.08}
  event=topic_alignment    stage=EXECUTED   gap=0.078 vel=+0.093 action=EXECUTE_CONVERGENCE
  event=response_risk      stage=EXECUTED   gap=0.044 vel=+0.071 action=EXECUTE_CONVERGENCE

============================================================
最終 Snapshot
  turn              : 5
  snapshot_version  : v0.9
  remaining capital : 997.24
  active events     : 10
  intent completed  : False

Action 集計
  NO_ACTION           : 0
  EXECUTE_CONVERGENCE : 10
  SAFETY_HALT         : 0
  total events generated : 10
  executor call count    : 10
============================================================
```

---

## 4. 観察と解釈

### 4.1 Gap の推移（topic_alignment）

| Turn | Gap | Velocity | 解釈 |
|------|-----|----------|------|
| 1 | 0.177 | 0.000 | 初期。目標からやや離れている |
| 2 | 0.293 | -0.036 | 軽微な逸脱開始。velocity が負に |
| 3 | **0.837** | **-0.185** | 大幅逸脱。gap 急増・velocity 強く負 |
| 4 | 0.227 | **+0.125** | ユーザー修正により回復。velocity が正に転じる |
| 5 | 0.078 | +0.093 | ほぼ目標圏内。収束方向 |

**重要点**: Turn 3 → Turn 4 で velocity が明確に正転している。  
DCK は「差異の変化率」を捉えており、単なる絶対値監視ではない。

### 4.2 Decision の傾向

- 全 10 イベントで `EXECUTE_CONVERGENCE` を選択
- `NO_ACTION` / `SAFETY_HALT` は一度も発生せず

これは設定（`max_gap_scale=1.0` など）を敏感側にしたため。  
より保守的な閾値にすれば、Turn 5 付近で `NO_ACTION` が出る可能性が高い。

### 4.3 リソース消費

- 初期 capital: 1000.0
- 最終 capital: 997.24
- 消費量 ≈ 2.76（10 回の小さな収束アクション）

gap に比例した軽量な消費になっている。

---

## 5. 現時点での示唆（PLP+PSS+Capsule+DCK 視点）

今回は DCK 単体の観察に留めたが、以下の点が確認できた：

1. **差異の変化率（velocity）が自然に現れる**  
   → 外部前頭葉的な「ズレ検知」の基盤になりうる。

2. **Intent を完了させない限り、継続的に収束アクションを出し続けられる**  
   → Capsule が「維持すべき状態」を供給し、DCK がそれを監視する構図と相性が良い。

3. **日常会話というノイズの多い入力でも、数値化された状態差異として扱える**  
   → Observer を LLM ベースに差し替えれば、実際の対話ログを直接流し込める。

次の段階で価値が出る検証は：

- Capsule が「現在維持すべき状態ベクトル」を明示的に供給した場合
- PSS が「差分仕様」を構造化した場合
- それらを DCK の Intent / Goal に直接マッピングした場合

に、LLM 単体の「広い探索」がどれだけ削減されるか、である。

---

## 6. 再現方法

```bash
PYTHONPATH=. python -m examples.conversation_demo
```

依存: Python ≥ 3.10, pydantic, numpy, scipy
