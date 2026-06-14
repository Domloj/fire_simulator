"""
Engine module for FFSim — core simulation logic.

Implements spec section 4 (simulation lifecycle) with:
- SimulationEngine: Main 7-phase tick orchestrator
- RNG manager for deterministic simulation
- Fire propagation model
- Agent management
- Telemetry generation and publishing
"""

from src.engine.simulation_engine import SimulationEngine, SimulationSnapshot
from src.engine.rng_manager import RngManager
from src.engine.agent_manager import AgentManager

__all__ = ["SimulationEngine", "SimulationSnapshot", "RngManager", "AgentManager"]
