# Difference Convergence Kernel (DCK)

«A model-neutral kernel for autonomous difference convergence.»

Difference Convergence Kernel (DCK) は、「目標状態と現在状態の差異（Difference）」を観測し、その差異を安全かつ効率的に収束させるための意思決定カーネルです。

DCK は AI エージェントに限定された設計ではありません。

ロボティクス、産業制御、クラウドオーケストレーション、シミュレーション、ゲーム AI、意思決定支援システムなど、「現在状態を目標状態へ収束させる」という問題であれば利用できます。

---

## Design Philosophy

DCK は以下の原則に基づいて設計されています。

- Difference First
- Intent Driven
- Resource Aware
- Predict Before Execute
- Capability Isolation
- Immutable Transition
- Deterministic Snapshot
- Model Neutral

DCK は特定の AI や機械学習アルゴリズムを前提としません。

Observer・Predictor・Executor を差し替えるだけで様々なシステムへ適用できます。

---

## Core Architecture

```text
Telemetry
     │
     ▼
Observer
     │
     ▼
StateEstimate
     │
     ▼
Predictor
     │
     ▼
TransitionEvent
     │
     ▼
Decision Engine
     │
     ▼
Resource Allocator
     │
     ▼
Lease Manager
     │
     ▼
Executor
     │
     ▼
Delayed Feedback
     │
     ▼
Difference Convergence
```

DCK はこの閉ループを繰り返すことで、状態を継続的に目標へ収束させます。

---

## Main Components

### DifferenceConvergenceKernel

システム全体を制御する中心コンポーネントです。

**責務**

- Telemetry 観測
- 状態推定
- 将来予測
- イベント生成
- 意思決定
- リソース管理
- 実行
- フィードバック反映
- スナップショット生成

---

### Intent Scheduler

Intent を優先順位・期限・依存関係に基づいて管理します。

**対応機能**

- Priority Aging
- Deadline
- Dependency Resolution
- Lifecycle Management

---

### Decision Engine

各イベントに対して

- `NO_ACTION`
- `EXECUTE_CONVERGENCE`
- `SAFETY_HALT`

を選択します。

標準実装では正規化 Potential 関数を使用します。

**評価対象**

- Difference
- Velocity
- Resource Congruence
- Risk

---

### Lease Manager

可逆・不可逆リソースを二段階で管理します。

**Reversible Resources**（一時予約可能）

- CPU
- GPU
- Memory
- Network

**Irreversible Resources**（実行後に消費される資源）

- Energy
- Money
- Time

二相コミット方式により、安全なリソース管理を実現します。

---

### Event Cache

イベントは二層構造で保存されます。

```text
Active Cache
        │
        ▼
Archive Cache
```

進行中イベントと完了イベントを分離することで高速な検索と履歴保持を両立しています。

---

### Snapshot

Kernel 全体を Point-in-Time 一貫性で取得できます。

Snapshot には以下が含まれます。

- Resources
- Intents
- Events
- Active Leases

---

## Extension Points

DCK は Protocol ベースの設計です。

ユーザーは以下を自由に差し替えられます。

- Observer
- Predictor
- Executor
- Decision Engine
- Resource Allocator
- Compensation Strategy
- Clock

これにより用途に応じた実装へ容易に拡張できます。

---

## Typical Execution Flow

```text
Observe
  ↓
Predict
  ↓
Generate TransitionEvent
  ↓
Evaluate Difference
  ↓
Allocate Resources
  ↓
Reserve Lease
  ↓
Execute
  ↓
Commit
  ↓
Receive Feedback
  ↓
Converged
```

---

## Why Difference?

多くのシステムは「行動」を中心に設計されています。

DCK はその逆で、

**「差異をどう減らすか」**

を中心概念として設計されています。

この考え方により、

- AI Agent
- Robot
- Production System
- Distributed Scheduler
- Cloud Automation
- Optimization
- Digital Twin

など、幅広い分野へ適用できます。

---

## Features

- Immutable Transition Events
- Intent-based Scheduling
- Resource-aware Execution
- Two-Phase Resource Reservation
- Protocol-based Architecture
- Deterministic Snapshot
- Parallel Execution
- Delayed Feedback Processing
- Risk-aware Decision Making
- Dependency-aware Intent Scheduling

---

## Example Use Cases

- Autonomous AI Agents
- Robotics
- Manufacturing Control
- Industrial Automation
- Cloud Resource Scheduling
- Digital Twin
- Simulation Platforms
- Multi-Agent Systems
- Operations Research
- Reinforcement Learning Infrastructure

---

## Repository Structure

```text
dck/
├── __init__.py
├── builder.py
├── config.py
├── core.py
├── decision.py
├── events.py
├── exceptions.py
├── intents.py
├── observation.py
├── resources.py
├── stubs.py          # テスト・デモ用スタブ
├── types.py
└── utils.py

examples/
└── basic_usage.py    # スタブを使った最小動作確認
```

---

## Quick Start

```python
from dck import KernelBuilder, DCKConfig, ResourceVector, ReversibleResource, IrreversibleResource
from dck.stubs import StubObserver, StubPredictor, StubExecutor

kernel = (
    KernelBuilder(
        initial_resources=ResourceVector(
            rev=ReversibleResource(compute_cpu=100.0, compute_gpu=8.0),
            irr=IrreversibleResource(capital_money=10000.0, energy_power=50.0),
        )
    )
    .with_config(DCKConfig())
    .with_capabilities(
        observer=StubObserver(),
        predictor=StubPredictor(),
        executor=StubExecutor(),
    )
    .build()
)

# await kernel.tick(turn, raw_telemetry)
```

詳細な動作確認は `python -m examples.basic_usage` を参照してください。

---

## Requirements

- Python ≥ 3.10
- pydantic ≥ 2.0
- numpy
- scipy

---

## License

See the LICENSE file for licensing information.

---

## Vision

DCK は「AI のためのカーネル」を目指しているわけではありません。

目標は、

**「Difference（差異）を安全・説明可能・資源制約を考慮しながら収束させるための汎用カーネル」**

を提供することです。

Observer・Predictor・Executor を変更するだけで、多様なドメインに適用できる設計を目指しています。
