"""DCK 移動平均・決定論プロバイダ"""
import math
from collections import deque
from datetime import datetime, timezone
from typing import Optional, Tuple, Protocol

class AbstractClock(Protocol):
    def __call__(self) -> datetime: ...

class StepTimeProvider:
    def __init__(self, start_time: datetime, step_seconds: float = 1.0):
        self._current = start_time
        self._step = step_seconds

    def __call__(self) -> datetime:
        now = self._current
        self._current = datetime.fromtimestamp(now.timestamp() + self._step, tz=timezone.utc)
        return now

class DeterministicIDGenerator:
    def __init__(self, kernel_id: str = "dck_k01", seed: Optional[int] = None):
        self._kernel_id = kernel_id
        self._counter = 0
        self._seed = seed

    def __call__(self, prefix: str) -> str:
        if self._seed is not None:
            self._counter += 1
            return f"{prefix}_{self._kernel_id}_{self._seed}_{self._counter:08d}"
        import uuid
        return f"{prefix}_{self._kernel_id}_{uuid.uuid4().hex[:12]}"

class GapHistory:
    def __init__(self, maxlen: int = 10, tau: float = 2.0):
        self.history: deque[Tuple[datetime, float]] = deque(maxlen=maxlen)
        self.tau = tau
        self._smoothed_velocity: float = 0.0

    def push(self, timestamp: datetime, gap: float) -> float:
        if not self.history:
            self.history.append((timestamp, gap))
            return 0.0

        prev_ts, prev_gap = self.history[-1]
        dt = (timestamp - prev_ts).total_seconds()
        self.history.append((timestamp, gap))

        if dt <= 1e-6:
            return self._smoothed_velocity

        raw_velocity = (prev_gap - gap) / dt
        alpha = 1.0 - math.exp(-dt / self.tau)
        self._smoothed_velocity = (alpha * raw_velocity) + ((1.0 - alpha) * self._smoothed_velocity)
        return self._smoothed_velocity
