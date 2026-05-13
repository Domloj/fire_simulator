from dataclasses import dataclass
from typing import Optional

from src.engine.models.core.location import Location
from src.engine.models.map.sector import Sector

@dataclass
class AgentPerception:
    """What agent can perceive from environment (for decision-making)"""
    current_location: Location
    current_sector: Optional[Sector]
    destination: Location
    distance_to_destination: float
    task_progress: float  
    base_location: Location
