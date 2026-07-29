"""DCK v0.9 環境設定とハイパーパラメータ"""
from pydantic import BaseModel, ConfigDict

class DCKConfig(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    
    max_gap_scale: float = 100.0
    max_risk_scale: float = 50.0
    target_velocity_scale: float = 10.0
    
    velocity_time_constant_tau: float = 2.0
    softplus_k: float = 5.0
    
    risk_safety_margin: float = 3.0
    aging_factor: float = 0.5
    transaction_timeout_sec: float = 30.0
    convergence_tolerance: float = 2.0
    
    max_concurrency_execution: int = 8
    
    psd_jitter: float = 1e-8
    min_uncertainty: float = 1e-12
    
    active_cache_capacity: int = 1000
    archive_cache_capacity: int = 5000
    gap_history_size: int = 10
    
    weight_equivalence: float = 1.0
    weight_velocity: float = 1.5
    weight_congruence: float = 0.5
    weight_risk: float = 1.0
