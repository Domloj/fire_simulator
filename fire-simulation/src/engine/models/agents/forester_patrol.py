import logging
from datetime import datetime
from typing import Optional

from src.engine.models.agents.agent import Agent
from src.engine.models.agents.agent_state import AgentState
from src.engine.models.core.location import Location
from src.engine.models.map.sector import Sector
from src.engine.models.agents.agent_state import AGENT_STATE

logger = logging.getLogger(__name__)

class ForesterPatrol(Agent):
    """Forester patrol agent - runtime only (no decision logic)"""
    
    def __init__(
        self,
        forester_patrol_id: str,
        timestamp: datetime,
        base_location: Location,
        initial_location: Location,
        initial_state: Optional[AgentState] = None,
    ):
        super().__init__(forester_patrol_id, timestamp, base_location, initial_location)
        self._patrol_duration = 60.0  # seconds to complete patrol
        self._patrol_elapsed = 0.0
        
        match initial_state:
            case AGENT_STATE.AVAILABLE:
                self._state = AgentState.IDLE
            case AGENT_STATE.TRAVELLING:
                self._state = AgentState.TRAVELING
            case AGENT_STATE.EXTINGUISHING:
                self._state = AgentState.EXECUTING
            case _:
                self._state = AgentState.IDLE
    
    def execute_task(self, delta: float, sector: Optional[Sector]) -> bool:
        """Patrol area - returns True when patrol complete"""
        self._patrol_elapsed += delta
        
        is_complete = self._patrol_elapsed >= self._patrol_duration
        
        if is_complete:
            logger.debug(f"ForesterPatrol {self._agent_id}: patrol complete")
            self._patrol_elapsed = 0.0  # Reset for next patrol
        
        return is_complete
    
    def get_task_progress(self, sector: Optional[Sector]) -> float:
        """Return patrol completion (0.0 - 1.0)"""
        return min(1.0, self._patrol_elapsed / self._patrol_duration)
    
    def can_execute_task(self, sector: Sector) -> bool:
        """Can patrol anywhere"""
        return True

    def allowed_task_types(self) -> set:
        """ForesterPatrol accepts move and patrol commands."""
        return {"move_to", "patrol", "return_to_base", "abort"}
    
    def increment_agents_in_sector(self, sector: Sector):
        """Track number of forester patrols in sector"""
        sector._number_of_forester_patrols += 1
    
    def decrement_agents_in_sector(self, sector: Sector):
        """Track number of forester patrols in sector"""
        sector._number_of_forester_patrols -= 1
    
    @property
    def forester_patrol_id(self) -> str:
        return self.agent_id
    
    # ===== BACKWARD COMPATIBILITY =====
    
    @property
    def initial_location(self) -> Location:
        """Deprecated: Use location instead"""
        return self._location
    
    def clone(self) -> 'ForesterPatrol':
        """Create a copy of this forester patrol"""
        return ForesterPatrol(
            forester_patrol_id=self._agent_id,
            timestamp=self._timestamp,
            base_location=Location(self._base_location.latitude, self._base_location.longitude),
            initial_location=Location(self._location.latitude, self._location.longitude),
            initial_state=self._state
        )
