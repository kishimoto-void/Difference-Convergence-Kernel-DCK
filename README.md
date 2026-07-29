# Difference Convergence Kernel (DCK) v0.9

**Difference Convergence Kernel** — resource-aware, intent-driven state convergence engine.

## Overview

DCK provides a structured runtime for:

- Intent scheduling with priority aging & dependency resolution
- Equivalence-gap based decision making (Normalized Potential Engine)
- Two-phase resource leasing (reversible / irreversible)
- Async parallel transaction execution with safety halt
- Point-in-time snapshots under dual locks

## Package Layout

```text
dck/
├── __init__.py
├── exceptions.py      # DCK dedicated exception hierarchy
├── config.py          # DCKConfig (Pydantic v2, frozen)
├── types.py           # ActionType, TransitionStage, CovarianceMatrix, StateEstimate
├── resources.py       # ResourceVector, LeaseManager (2PC + async context)
├── events.py          # TransitionEvent, TwoTierEventCache, KernelSnapshot
├── intents.py         # Intent, IntentRecord, IntentScheduler
├── observation.py     # Protocol-based capabilities (Observer / Predictor / Executor)
├── decision.py        # IResourceAllocator, NormalizedPotentialEngine
├── utils.py           # StepTimeProvider, DeterministicIDGenerator, GapHistory
├── builder.py         # KernelBuilder (DI style)
└── core.py            # DifferenceConvergenceKernel (main loop)
```

## Requirements

- Python ≥ 3.10
- pydantic ≥ 2.0
- numpy
- scipy

## Quick Start (Builder pattern)

```python
from dck import KernelBuilder, DCKConfig, ResourceVector, ReversibleResource, IrreversibleResource

# supply your own Observer / Predictor / Executor implementations
kernel = (
    KernelBuilder(
        initial_resources=ResourceVector(
            rev=ReversibleResource(compute_cpu=100.0, compute_gpu=8.0),
            irr=IrreversibleResource(capital_money=10000.0, energy_power=50.0),
        )
    )
    .with_config(DCKConfig())
    .with_capabilities(observer=..., predictor=..., executor=...)
    .build()
)

# then: await kernel.tick(turn, raw_telemetry)
```

## License

Research / non-commercial use preferred (follow repository license if added later).
