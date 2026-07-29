"""DCK テスト・デモ用スタブ実装

Protocol (IObserverCapability / IPredictorCapability / IExecutorCapability) を満たす
最小実装。本番ロジックの検証や KernelBuilder の動作確認に使用する。
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, Any
import numpy as np

from dck.types import StateEstimate, CovarianceMatrix, ActionType
from dck.resources import ResourceVector
from dck.events import TransitionEvent


class StubObserver:
    """テレメトリをそのまま 1次元 StateEstimate に変換する簡易 Observer"""

    async def observe(self, raw_telemetry: Dict[str, Any]) -> Dict[str, StateEstimate]:
        now = datetime.now(timezone.utc)
        result: Dict[str, StateEstimate] = {}

        for metric, value in raw_telemetry.items():
            try:
                val = float(value)
            except (TypeError, ValueError):
                val = 0.0

            mean = np.array([val], dtype=np.float64)
            # 小さな不確実性を付与
            cov = CovarianceMatrix(matrix=np.array([[0.25]], dtype=np.float64))
            result[metric] = StateEstimate(
                mean=mean,
                covariance=cov,
                confidence=0.95,
                timestamp=now,
                source="stub_observer",
            )
        return result


class StubPredictor:
    """観測値をほぼ保持する簡易 Predictor（horizon に応じてわずかに減衰）"""

    def __init__(self, drift: float = 0.0):
        self.drift = drift

    async def forecast(
        self, metric_name: str, est: StateEstimate, horizon: int
    ) -> StateEstimate:
        # 決定論的な簡易投影（テスト再現性のためランダムを使わない）
        decay = max(0.5, 1.0 - 0.02 * horizon)
        new_mean = est.mean * decay + self.drift

        # 不確実性を horizon に比例して少し増やす
        base_var = float(est.covariance.matrix[0, 0]) if est.covariance.matrix.size > 0 else 0.25
        new_var = base_var * (1.0 + 0.1 * horizon)
        new_cov = CovarianceMatrix(matrix=np.array([[new_var]], dtype=np.float64))

        return StateEstimate(
            mean=new_mean.astype(np.float64),
            covariance=new_cov,
            confidence=max(0.1, est.confidence - 0.03 * horizon),
            timestamp=est.timestamp,
            source="stub_predictor",
        )


class StubExecutor:
    """常に成功を返す簡易 Executor（副作用なし）"""

    def __init__(self, always_succeed: bool = True):
        self.always_succeed = always_succeed
        self.call_count = 0

    async def execute(self, action: ActionType, resource: ResourceVector) -> bool:
        self.call_count += 1
        return self.always_succeed


class FailingExecutor(StubExecutor):
    """常に失敗する Executor（失敗パス検証用）"""

    def __init__(self):
        super().__init__(always_succeed=False)
