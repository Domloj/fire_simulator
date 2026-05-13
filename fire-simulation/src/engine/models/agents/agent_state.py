from enum import Enum

class AgentState(str, Enum):
    """Physical state of agent in simulation (NOT decision state)"""
    IDLE = "idle"              # At base, waiting for orders
    TRAVELING = "traveling"    # Moving to destination
    EXECUTING = "executing"    # Performing task (extinguishing/patrolling)
    RETURNING = "returning"    # Moving back to base

class AGENT_STATE(Enum):
    AVAILABLE = 1
    TRAVELLING = 2
    EXTINGUISHING = 3
