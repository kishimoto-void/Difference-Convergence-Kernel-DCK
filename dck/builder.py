"""DCK Kernel 構成用の DI Builder"""
import logging
from typing import Optional, Callable
from datetime import datetime, timezone
from dck.config import DCKConfig
from dck.resources import ResourceVector
from dck.observation import IObserverCapability, IPredictorCapability, IExecutorCapability, AbstractCompensationStrategy, DefaultCompensationStrategy
from dck.decision import DecisionEngine, IResourceAllocator, DefaultResourceAllocator, NormalizedPotentialEngine

class KernelBuilder:
    def __init__(self, initial_resources: ResourceVector):
        self._resources = initial_resources
        self._config = DCKConfig()
        self._observer: Optional[IObserverCapability] = None
        self._predictor: Optional[IPredictorCapability] = None
        self._executor: Optional[IExecutorCapability] = None
        self._allocator: IResourceAllocator = DefaultResourceAllocator()
        self._compensation: AbstractCompensationStrategy = DefaultCompensationStrategy()
        self._decision_engine: DecisionEngine = NormalizedPotentialEngine()
        self._clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
        self._kernel_id: str = "dck_k01"
        self._logger: Optional[logging.Logger] = None

    def with_config(self, config: DCKConfig) -> "KernelBuilder":
        self._config = config
        return self

    def with_capabilities(
        self, observer: IObserverCapability, predictor: IPredictorCapability, executor: IExecutorCapability
    ) -> "KernelBuilder":
        self._observer = observer
        self._predictor = predictor
        self._executor = executor
        return self

    def with_allocator(self, allocator: IResourceAllocator) -> "KernelBuilder":
        self._allocator = allocator
        return self

    def with_compensation_strategy(self, strategy: AbstractCompensationStrategy) -> "KernelBuilder":
        self._compensation = strategy
        return self

    def with_decision_engine(self, engine: DecisionEngine) -> "KernelBuilder":
        self._decision_engine = engine
        return self

    def with_clock(self, clock: Callable[[], datetime]) -> "KernelBuilder":
        self._clock = clock
        return self

    def with_kernel_id(self, kernel_id: str) -> "KernelBuilder":
        self._kernel_id = kernel_id
        return self

    def with_logger(self, logger: logging.Logger) -> "KernelBuilder":
        self._logger = logger
        return self

    def build(self) -> "DifferenceConvergenceKernel":
        from dck.core import DifferenceConvergenceKernel
        if not self._observer or not self._predictor or not self._executor:
            raise ValueError("Observer, Predictor, and Executor capabilities must be provided.")

        return DifferenceConvergenceKernel(
            system_resources=self._resources,
            observer=self._observer,
            predictor=self._predictor,
            executor=self._executor,
            resource_allocator=self._allocator,
            compensation_strategy=self._compensation,
            config=self._config,
            decision_engine=self._decision_engine,
            time_provider=self._clock,
            kernel_id=self._kernel_id,
            logger_instance=self._logger
        )
