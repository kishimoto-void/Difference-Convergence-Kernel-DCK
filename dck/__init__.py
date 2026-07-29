"""Difference Convergence Kernel (DCK) v0.9

Difference Convergence Kernel - A resource-aware, intent-driven state convergence engine.
"""

__version__ = "0.9.0"

from dck.core import DifferenceConvergenceKernel
from dck.builder import KernelBuilder
from dck.config import DCKConfig
from dck.resources import ResourceVector, ReversibleResource, IrreversibleResource
from dck.types import ActionType, TransitionStage, StateEstimate, CovarianceMatrix
from dck.intents import Intent, MetricGoal
from dck.events import TransitionEvent, KernelSnapshot

__all__ = [
    "DifferenceConvergenceKernel",
    "KernelBuilder",
    "DCKConfig",
    "ResourceVector",
    "ReversibleResource",
    "IrreversibleResource",
    "ActionType",
    "TransitionStage",
    "StateEstimate",
    "CovarianceMatrix",
    "Intent",
    "MetricGoal",
    "TransitionEvent",
    "KernelSnapshot",
]
