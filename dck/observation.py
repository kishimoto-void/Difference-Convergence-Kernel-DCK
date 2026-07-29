"""DCK Protocol ベース Capability インターフェース"""
from typing import Protocol, Dict, Any
from dck.types import StateEstimate, ActionType, ResourceVector
from dck.events import TransitionEvent

class IObserverCapability(Protocol):
    async def observe(self, raw_telemetry: Dict[str, Any]) -> Dict[str, StateEstimate]: ...

class IPredictorCapability(Protocol):
    async def forecast(self, metric_name: str, est: StateEstimate, horizon: int) -> StateEstimate: ...

class IExecutorCapability(Protocol):
    async def execute(self, action: ActionType, resource: ResourceVector) -> bool: ...

class AbstractCompensationStrategy(Protocol):
    async def compensate(self, event: TransitionEvent, allocated_resource: ResourceVector) -> bool: ...

class DefaultCompensationStrategy:
    async def compensate(self, event: TransitionEvent, allocated_resource: ResourceVector) -> bool:
        return True
