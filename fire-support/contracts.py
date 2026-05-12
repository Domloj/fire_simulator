"""
Data contracts defining the structure of data exchanged between services.

This module defines the expected data structures for:
- Recommendations sent to frontend
- State updates received from simulation
- Configuration messages
"""

from typing import Dict, List, Optional, TypedDict, Union


class RecommendedAction(TypedDict, total=False):
    """Single recommended action for a unit"""
    unitId: int
    sectorId: int
    unitType: str  # "fireBrigade" or "foresterPatrol" - REQUIRED to avoid ID conflicts
    description: str  # Task description for agent deduplication
    priority: int  # Task priority (higher = more important)
    reasoning: Optional[str]  # Explain why this action was recommended


class RecommendationMessage(TypedDict):
    """Complete recommendation message sent to frontend/backend"""
    timestamp: float  # Unix timestamp in seconds
    recommendedActions: List[RecommendedAction]
    priority: str  # "LOW", "MEDIUM", "HIGH"


class SectorStateUpdate(TypedDict, total=False):
    """Minimal sector state update - only changed fields"""
    sectorId: int
    state: Dict  # Contains fireLevel, burnLevel, extinguishLevel, fireState
    # Optional: only include if changed
    fireLevel: Optional[float]
    burnLevel: Optional[float]
    extinguishLevel: Optional[float]


class SectorFullState(TypedDict):
    """Full sector state (used when full update needed)"""
    sectorId: int
    state: Dict
    row: Optional[int]
    column: Optional[int]
    sectorType: Optional[str]


class FireBrigadeStateUpdate(TypedDict, total=False):
    """Minimal fire brigade state update"""
    fireBrigadeId: int
    state: str  # "AVAILABLE", "TRAVELLING", "EXTINGUISHING"
    location: Dict  # {latitude: float, longitude: float}


class ForesterPatrolStateUpdate(TypedDict, total=False):
    """Minimal forester patrol state update"""
    foresterPatrolId: int
    state: str  # "AVAILABLE", "TRAVELLING", "PATROLLING"
    location: Dict  # {latitude: float, longitude: float}


class ConfigurationMessage(TypedDict):
    """Forest configuration message"""
    forestId: str
    forestName: str
    location: List[Dict]  # Four corner locations
    rows: int
    columns: int
    sectors: List[Dict]
    fireBrigades: List[Dict]
    foresterPatrols: List[Dict]
    sensors: Optional[List[Dict]]
    cameras: Optional[List[Dict]]


class StateUpdateMessage(TypedDict, total=False):
    """Aggregated state update message from simulation"""
    sectors: Union[Dict[int, SectorFullState], List[SectorFullState]]
    fireBrigades: Union[Dict[int, FireBrigadeStateUpdate], List[FireBrigadeStateUpdate]]
    foresterPatrols: Union[Dict[int, ForesterPatrolStateUpdate], List[ForesterPatrolStateUpdate]]


# Queue routing keys and contracts
QUEUE_CONTRACTS = {
    "support.data.aggregated": {
        "description": "Receives aggregated state updates and configuration from simulation",
        "message_types": [ConfigurationMessage, StateUpdateMessage],
        "required_fields": {
            "config": ["forestId", "location", "rows", "columns"],
            "state": ["sectors", "fireBrigades"]
        }
    },
    "support.recommendations": {
        "description": "Publishes recommendations to backend/frontend",
        "message_type": RecommendationMessage,
        "required_fields": ["timestamp", "recommendedActions", "priority"]
    },
    "simulation.recommendations": {
        "description": "Receives recommendations from simulation (forwarded to backend)",
        "message_type": RecommendationMessage,
        "required_fields": ["timestamp", "recommendedActions"]
    }
}


def validate_recommendation_message(message: Dict) -> bool:
    """Validate recommendation message structure"""
    required = ["timestamp", "recommendedActions", "priority"]
    if not all(key in message for key in required):
        return False
    
    if not isinstance(message["recommendedActions"], list):
        return False
    
    for action in message["recommendedActions"]:
        if not isinstance(action, dict):
            return False
        if "unitId" not in action or "sectorId" not in action:
            return False
        if not isinstance(action["unitId"], (int, str)):
            return False
        if not isinstance(action["sectorId"], (int, str)):
            return False
        # unitType is required to distinguish fire brigades from forester patrols
        if "unitType" not in action:
            return False
        if action["unitType"] not in ["fireBrigade", "foresterPatrol"]:
            return False
    
    return True


def validate_state_update(message: Dict) -> bool:
    """Validate state update message structure"""
    # Must have at least one of sectors, fireBrigades, or foresterPatrols
    has_state = any(key in message for key in ["sectors", "fireBrigades", "foresterPatrols"])
    has_config = "location" in message and ("forestId" in message or "forestName" in message)
    
    return has_state or has_config


def extract_minimal_sector_update(sector_state: Dict) -> SectorStateUpdate:
    """Extract only necessary fields for sector update"""
    return {
        "sectorId": sector_state.get("sectorId"),
        "state": sector_state.get("state", {})
    }


def extract_minimal_brigade_update(brigade_state: Dict) -> FireBrigadeStateUpdate:
    """Extract only necessary fields for fire brigade update"""
    return {
        "fireBrigadeId": brigade_state.get("fireBrigadeId") or brigade_state.get("id"),
        "state": brigade_state.get("state"),
        "location": brigade_state.get("location", {})
    }


def extract_minimal_patrol_update(patrol_state: Dict) -> ForesterPatrolStateUpdate:
    """Extract only necessary fields for forester patrol update"""
    return {
        "foresterPatrolId": patrol_state.get("foresterPatrolId") or patrol_state.get("id"),
        "state": patrol_state.get("state"),
        "location": patrol_state.get("location", {})
    }
