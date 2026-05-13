from abc import ABC, abstractmethod

class SimulationEngine(ABC):
    @abstractmethod
    async def start(self) -> None:
        pass

    @abstractmethod
    async def stop(self) -> None:
        pass

    @abstractmethod
    async def step(self, ticks: int = 1) -> None:
        pass

    @abstractmethod
    async def pause(self) -> None:
        pass

    @abstractmethod
    async def load_config(self, config: dict) -> None:
        pass

    @abstractmethod
    def snapshot(self) -> dict:
        pass

    @abstractmethod
    def is_running(self) -> bool:
        pass
