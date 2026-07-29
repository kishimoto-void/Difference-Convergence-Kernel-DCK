"""DCK Intent, IntentRecord, IntentScheduler"""
from __future__ import annotations
import math
from enum import Enum
from typing import Dict, List, Optional, Tuple, Self
from pydantic import BaseModel, Field, ConfigDict
from dck.config import DCKConfig

class IntentLifecycleState(str, Enum):
    READY = "READY"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"

class MetricGoal(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    target_value: float
    tolerance: float = 1.0

class Intent(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    intent_id: str
    description: str
    goals: Dict[str, MetricGoal]
    time_horizon: int = Field(gt=0)
    created_turn: int
    base_priority: float = Field(ge=0.0, default=1.0)
    deadline_turn: Optional[int] = None
    dependencies: Tuple[str, ...] = Field(default_factory=tuple)

    def effective_priority(self, current_turn: int, config: DCKConfig) -> float:
        age = max(0, current_turn - self.created_turn)
        aging = math.log1p(age) * config.aging_factor
        deadline_factor = 1.0
        if self.deadline_turn:
            remaining = max(1, self.deadline_turn - current_turn)
            deadline_factor = max(0.1, remaining / 10.0)
        return self.base_priority + (aging / deadline_factor)

class IntentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    intent: Intent
    state: IntentLifecycleState = IntentLifecycleState.READY
    is_completed: bool = False

    def with_state(self, new_state: IntentLifecycleState) -> Self:
        return self.model_copy(update={"state": new_state})

    def with_completed(self) -> Self:
        return self.model_copy(update={"is_completed": True})

class IntentScheduler:
    def __init__(self, config: DCKConfig):
        self.config = config
        self._records: Dict[str, IntentRecord] = {}

    def submit(self, intent: Intent) -> None:
        rec = IntentRecord(intent=intent, state=IntentLifecycleState.READY, is_completed=False)
        self._records[intent.intent_id] = rec

    def get_runnable(self, current_turn: int) -> List[IntentRecord]:
        completed_ids = {r.intent.intent_id for r in self._records.values() if r.is_completed}
        
        runnable = []
        for rec in self._records.values():
            if rec.is_completed:
                continue
            if rec.state in (IntentLifecycleState.READY, IntentLifecycleState.ACTIVE):
                if rec.intent.deadline_turn and current_turn > rec.intent.deadline_turn:
                    continue
                if all(dep in completed_ids for dep in rec.intent.dependencies):
                    runnable.append(rec)

        return sorted(
            runnable,
            key=lambda x: x.intent.effective_priority(current_turn, self.config),
            reverse=True
        )

    def mark_active(self, intent_ids: List[str]) -> None:
        for i_id in intent_ids:
            rec = self._records.get(i_id)
            if rec and rec.state == IntentLifecycleState.READY:
                self._records[i_id] = rec.with_state(IntentLifecycleState.ACTIVE)

    def mark_completed(self, intent_id: str) -> None:
        rec = self._records.get(intent_id)
        if rec:
            self._records[intent_id] = rec.with_completed()

    def get_record(self, intent_id: str) -> Optional[IntentRecord]:
        return self._records.get(intent_id)

    def get_all_records(self) -> Dict[str, IntentRecord]:
        return dict(self._records)
