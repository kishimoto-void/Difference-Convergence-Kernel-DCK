"""DCK 不変TransitionEvent, 2階層キャッシュ, Snapshot構造体 (v0.9)"""
from __future__ import annotations
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Optional, Self
import numpy as np
from pydantic import BaseModel, Field, ConfigDict
from dck.types import StateEstimate, TransitionStage, ActionType
from dck.resources import ResourceVector, LeaseRecord
from dck.intents import IntentRecord

class TransitionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    event_id: str
    intent_id: str
    metric_name: str
    expected_state: float
    observed_state: StateEstimate
    projected_state: StateEstimate
    created_turn: int
    created_at: datetime
    lease_id: Optional[str] = None
    decision_action: Optional[ActionType] = None
    actual_state: Optional[float] = None
    current_stage: TransitionStage = TransitionStage.INITIATED
    computed_velocity: float = 0.0

    def compute_equivalence_gap(self) -> float:
        target_vec = np.array([self.expected_state], dtype=np.float64)
        if self.projected_state.mean.shape[0] == 1:
            return self.projected_state.mahalanobis_distance(target_vec)
        return abs(self.expected_state - float(self.projected_state.mean[0]))

    def compute_risk_score(self, min_uncertainty: float) -> float:
        return self.projected_state.total_uncertainty(min_uncertainty)

    def with_stage(self, stage: TransitionStage, **updates) -> Self:
        updates["current_stage"] = stage
        return self.model_copy(update=updates)

class KernelSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    turn: int
    system_resources: ResourceVector
    intent_records: Dict[str, IntentRecord]
    active_events: Dict[str, TransitionEvent]
    active_leases: Dict[str, LeaseRecord]
    snapshot_version: str = "v0.9"
    timestamp: datetime

class TwoTierEventCache:
    def __init__(self, active_capacity: int = 1000, archive_capacity: int = 5000):
        self.active_capacity = active_capacity
        self.archive_capacity = archive_capacity
        self.active_events: OrderedDict[str, TransitionEvent] = OrderedDict()
        self.archived_events: OrderedDict[str, TransitionEvent] = OrderedDict()

    def put(self, event: TransitionEvent) -> None:
        e_id = event.event_id
        if event.current_stage.is_terminal:
            self.active_events.pop(e_id, None)
            if e_id in self.archived_events:
                self.archived_events.move_to_end(e_id)
            self.archived_events[e_id] = event
            if len(self.archived_events) > self.archive_capacity:
                self.archived_events.popitem(last=False)
        else:
            if e_id in self.active_events:
                self.active_events.move_to_end(e_id)
            self.active_events[e_id] = event
            if len(self.active_events) > self.active_capacity:
                ev_id, ev = self.active_events.popitem(last=False)
                self.archived_events[ev_id] = ev

    def get(self, event_id: str) -> Optional[TransitionEvent]:
        if event_id in self.active_events:
            self.active_events.move_to_end(event_id)
            return self.active_events[event_id]
        if event_id in self.archived_events:
            self.archived_events.move_to_end(event_id)
            return self.archived_events[event_id]
        return None

    def all_events(self) -> Dict[str, TransitionEvent]:
        merged = dict(self.archived_events)
        merged.update(self.active_events)
        return merged
