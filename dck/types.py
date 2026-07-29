"""DCK 基本型、列挙型、不変値オブジェクト"""
from datetime import datetime
from enum import Enum
from typing import Any
import math
import scipy.linalg
import numpy as np
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr, field_validator

class ActionType(str, Enum):
    NO_ACTION = "NO_ACTION"
    EXECUTE_CONVERGENCE = "EXECUTE_CONVERGENCE"
    SAFETY_HALT = "SAFETY_HALT"

class TransitionStage(str, Enum):
    INITIATED = "INITIATED"
    PROJECTED = "PROJECTED"
    EXECUTED = "EXECUTED"
    CONVERGED = "CONVERGED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in (TransitionStage.CONVERGED, TransitionStage.FAILED)

class CovarianceMatrix(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    matrix: np.ndarray = Field(..., description="対称正定値共分散行列 (N, N)")
    _cholesky_L: np.ndarray = PrivateAttr()

    @field_validator("matrix")
    @classmethod
    def validate_matrix(cls, v: Any) -> np.ndarray:
        if not isinstance(v, np.ndarray) or v.ndim != 2 or v.shape[0] != v.shape[1]:
            raise ValueError("Covariance matrix must be a square 2D numpy ndarray.")
        
        v_sq = (v + v.T) / 2.0
        min_eig = np.min(np.linalg.eigvalsh(v_sq))
        if min_eig < 1e-8:
            jitter = (1e-8 - min_eig) if min_eig < 0 else 1e-8
            v_sq += np.eye(v_sq.shape[0]) * jitter
        return v_sq.astype(np.float64)

    def model_post_init(self, __context: Any) -> None:
        self._cholesky_L = np.linalg.cholesky(self.matrix)

    @property
    def cholesky_L(self) -> np.ndarray:
        return self._cholesky_L

class StateEstimate(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    mean: np.ndarray = Field(..., description="状態推定平均ベクトル (N,)")
    covariance: CovarianceMatrix = Field(..., description="共分散行列オブジェクト")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: datetime = Field(..., description="観測タイムスタンプ")
    source: str = "dck_observer"

    @field_validator("mean")
    @classmethod
    def validate_mean(cls, v: Any) -> np.ndarray:
        if not isinstance(v, np.ndarray) or v.ndim != 1:
            raise ValueError("Mean must be a 1D numpy ndarray.")
        return v.astype(np.float64)

    def mahalanobis_distance(self, target_mean: np.ndarray) -> float:
        diff = self.mean - target_mean
        try:
            y = scipy.linalg.solve_triangular(self.covariance.cholesky_L, diff, lower=True)
            return float(np.linalg.norm(y))
        except Exception:
            return float(np.linalg.norm(diff))

    def total_uncertainty(self, min_uncertainty: float = 1e-12) -> float:
        sign, logdet = np.linalg.slogdet(self.covariance.matrix)
        if sign <= 0:
            return min_uncertainty
        return max(min_uncertainty, math.exp(0.5 * logdet))
