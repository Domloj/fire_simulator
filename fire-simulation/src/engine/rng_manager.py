"""
RNG Manager - Single source of randomness for deterministic simulation.

According to FFSim spec 2.3:
- All randomness comes from one RNG generator
- RNG state is part of simulation snapshot
- Forbidden: Math.random(), local RNG, non-deterministic time sources
"""

import numpy as np
from typing import Optional


class RngManager:
    """Deterministic random number generator for FFSim."""

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize RNG manager with optional seed.

        Args:
            seed: Optional seed for reproducibility. If None, random seed is used.
        """
        if seed is None:
            seed = np.random.randint(0, 2**32 - 1)
        
        self.seed = seed
        self.rng = np.random.RandomState(seed)
        self.call_count = 0  # Track RNG calls for debugging

    def random(self) -> float:
        """
        Generate random float in [0, 1).

        Returns:
            Random float value
        """
        self.call_count += 1
        return self.rng.random()

    def randint(self, low: int, high: int) -> int:
        """
        Generate random integer in [low, high).

        Args:
            low: Inclusive lower bound
            high: Exclusive upper bound

        Returns:
            Random integer value
        """
        self.call_count += 1
        return self.rng.randint(low, high)

    def uniform(self, low: float, high: float) -> float:
        """
        Generate random float in [low, high).

        Args:
            low: Inclusive lower bound
            high: Exclusive upper bound

        Returns:
            Random float value
        """
        self.call_count += 1
        return self.rng.uniform(low, high)

    def normal(self, mean: float = 0.0, std: float = 1.0) -> float:
        """
        Generate random value from normal distribution.

        Args:
            mean: Mean of distribution
            std: Standard deviation of distribution

        Returns:
            Random float value
        """
        self.call_count += 1
        return self.rng.normal(mean, std)

    def choice(self, arr, size: int = 1, replace: bool = False):
        """
        Random choice from array.

        Args:
            arr: Array to choose from
            size: Number of choices
            replace: Whether to allow replacement

        Returns:
            Selected element(s)
        """
        self.call_count += 1
        return self.rng.choice(arr, size=size, replace=replace)

    def get_state(self) -> dict:
        """
        Get RNG state for snapshot.

        Returns:
            Dictionary with RNG state
        """
        return {
            "seed": self.seed,
            "call_count": self.call_count,
            "rng_state": self.rng.get_state()
        }

    def set_state(self, state: dict) -> None:
        """
        Restore RNG state from snapshot.

        Args:
            state: Dictionary with RNG state
        """
        self.seed = state["seed"]
        self.call_count = state["call_count"]
        self.rng.set_state(state["rng_state"])

    def __repr__(self) -> str:
        return f"RngManager(seed={self.seed}, calls={self.call_count})"
