"""DCK 可逆/不可逆リソース及び2フェーズ・コミット対応 LeaseManager"""
from __future__ import annotations
import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Self, Any
from pydantic import BaseModel, Field, ConfigDict
from dck.exceptions import ResourceExhaustedError

class ReversibleResource(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    compute_cpu: float = Field(ge=0.0, default=0.0)
    compute_gpu: float = Field(ge=0.0, default=0.0)
    bandwidth: float = Field(ge=0.0, default=0.0)

    def is_sufficient_for(self, required: ReversibleResource) -> bool:
        return (self.compute_cpu >= required.compute_cpu and
                self.compute_gpu >= required.compute_gpu and
                self.bandwidth >= required.bandwidth)

    def add(self, other: ReversibleResource) -> ReversibleResource:
        return ReversibleResource(
            compute_cpu=self.compute_cpu + other.compute_cpu,
            compute_gpu=self.compute_gpu + other.compute_gpu,
            bandwidth=self.bandwidth + other.bandwidth,
        )

    def subtract(self, other: ReversibleResource) -> ReversibleResource:
        if not self.is_sufficient_for(other):
            raise ResourceExhaustedError("Insufficient reversible resources.")
        return ReversibleResource(
            compute_cpu=self.compute_cpu - other.compute_cpu,
            compute_gpu=self.compute_gpu - other.compute_gpu,
            bandwidth=self.bandwidth - other.bandwidth,
        )

class IrreversibleResource(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    capital_money: float = Field(ge=0.0, default=0.0)
    energy_power: float = Field(ge=0.0, default=0.0)
    time_window: float = Field(ge=0.0, default=0.0)

    def is_sufficient_for(self, required: IrreversibleResource) -> bool:
        return (self.capital_money >= required.capital_money and
                self.energy_power >= required.energy_power and
                self.time_window >= required.time_window)

    def subtract(self, other: IrreversibleResource) -> IrreversibleResource:
        if not self.is_sufficient_for(other):
            raise ResourceExhaustedError("Insufficient irreversible resources.")
        return IrreversibleResource(
            capital_money=self.capital_money - other.capital_money,
            energy_power=self.energy_power - other.energy_power,
            time_window=self.time_window - other.time_window,
        )

class ResourceVector(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    rev: ReversibleResource = Field(default_factory=ReversibleResource)
    irr: IrreversibleResource = Field(default_factory=IrreversibleResource)

    def congruence_index(self, required: ResourceVector) -> float:
        ratios = []
        if required.rev.compute_cpu > 0: ratios.append(self.rev.compute_cpu / required.rev.compute_cpu)
        if required.rev.compute_gpu > 0: ratios.append(self.rev.compute_gpu / required.rev.compute_gpu)
        if required.rev.bandwidth > 0: ratios.append(self.rev.bandwidth / required.rev.bandwidth)
        if required.irr.capital_money > 0: ratios.append(self.irr.capital_money / required.irr.capital_money)
        if required.irr.energy_power > 0: ratios.append(self.irr.energy_power / required.irr.energy_power)
        
        if not ratios:
            return 10.0
        if any(r <= 0.0 for r in ratios):
            return 0.0

        harmonic_mean = len(ratios) / sum(1.0 / r for r in ratios)
        return min(10.0, harmonic_mean)

class LeaseState(str, Enum):
    RESERVED = "RESERVED"
    ACTIVATED = "ACTIVATED"
    RELEASED = "RELEASED"
    CANCELLED = "CANCELLED"

class LeaseRecord(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    lease_id: str
    event_id: str
    reserved_resource: ResourceVector
    state: LeaseState
    created_at: datetime

class ResourceReservation:
    """DCK 2-Phase Commit用 予約トークン（Async Context Manager対応）"""
    def __init__(self, lease_id: str, event_id: str, resource: ResourceVector, manager: LeaseManager):
        self.lease_id = lease_id
        self.event_id = event_id
        self.resource = resource
        self._manager = manager
        self._is_committed = False
        self._is_cancelled = False

    async def commit_irreversible(self) -> bool:
        if self._is_committed or self._is_cancelled:
            return False
        success = await self._manager.commit_irreversible(self.lease_id)
        if success:
            self._is_committed = True
        return success

    async def cancel_reversible(self) -> bool:
        if self._is_cancelled or self._is_committed:
            return False
        success = await self._manager.cancel_reversible(self.lease_id)
        if success:
            self._is_cancelled = True
        return success

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if not self._is_committed and not self._is_cancelled:
            await self.cancel_reversible()

class LeaseManager:
    def __init__(self, initial_resources: ResourceVector):
        self._current = initial_resources
        self.lock = asyncio.Lock()
        self._active_leases: Dict[str, LeaseRecord] = {}

    @property
    def current_resources(self) -> ResourceVector:
        return self._current

    def get_lease_reserved_resource(self, lease_id: str) -> Optional[ResourceVector]:
        record = self._active_leases.get(lease_id)
        return record.reserved_resource if record else None

    def get_all_leases(self) -> Dict[str, LeaseRecord]:
        return dict(self._active_leases)

    async def reserve_reversible(self, lease_id: str, event_id: str, required: ResourceVector, now: datetime) -> Optional[ResourceReservation]:
        async with self.lock:
            if not self._current.rev.is_sufficient_for(required.rev):
                return None

            try:
                new_rev = self._current.rev.subtract(required.rev)
            except ResourceExhaustedError:
                return None

            self._current = ResourceVector(rev=new_rev, irr=self._current.irr)
            record = LeaseRecord(
                lease_id=lease_id,
                event_id=event_id,
                reserved_resource=required,
                state=LeaseState.RESERVED,
                created_at=now
            )
            self._active_leases[lease_id] = record
            return ResourceReservation(lease_id, event_id, required, self)

    async def commit_irreversible(self, lease_id: str) -> bool:
        async with self.lock:
            record = self._active_leases.get(lease_id)
            if not record or record.state != LeaseState.RESERVED:
                return False

            if not self._current.irr.is_sufficient_for(record.reserved_resource.irr):
                return False

            try:
                new_irr = self._current.irr.subtract(record.reserved_resource.irr)
            except ResourceExhaustedError:
                return False

            self._current = ResourceVector(rev=self._current.rev, irr=new_irr)
            self._active_leases[lease_id] = LeaseRecord(
                lease_id=record.lease_id,
                event_id=record.event_id,
                reserved_resource=record.reserved_resource,
                state=LeaseState.ACTIVATED,
                created_at=record.created_at
            )
            return True

    async def release(self, lease_id: str) -> bool:
        async with self.lock:
            record = self._active_leases.pop(lease_id, None)
            if not record or record.state in (LeaseState.RELEASED, LeaseState.CANCELLED):
                return False

            new_rev = self._current.rev.add(record.reserved_resource.rev)
            self._current = ResourceVector(rev=new_rev, irr=self._current.irr)
            return True

    async def cancel_reversible(self, lease_id: str) -> bool:
        return await self.release(lease_id)
