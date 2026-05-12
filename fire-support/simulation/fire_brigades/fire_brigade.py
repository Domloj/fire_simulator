import logging
from datetime import datetime
import json
from typing import Dict, Any, List, Optional

from simulation.sectors.sector import Sector
from simulation.agent import Agent
from simulation.location import Location
from simulation.agent_state import AGENT_STATE

logger = logging.getLogger(__name__)

class FireBrigade(Agent):
    def __init__(
        self,
        fire_brigade_id: str,
        timestamp: datetime,
        initial_state: AGENT_STATE,
        base_location: Location,
        initial_location: Location,
        llm_client=None,
        agent_communication=None,
    ):
        Agent.__init__(self, timestamp, base_location, initial_location)
        self._fire_brigade_id = fire_brigade_id
        self._state = initial_state
        self._destination = initial_location
        self._initial_location = initial_location
        self._base_location = base_location
        self._timestamp = timestamp
        self._llm_client = llm_client
        self._agent_communication = agent_communication
        self._current_target_sector_id = None
        self._extinguishing_rate = 2.0 # Fire level reduction per second (synced with simulation engine)

    @property
    def fire_brigade_id(self) -> str:
        return self._fire_brigade_id
    
    def extinguish(self, delta: float, sector: Sector) -> bool:
        """Extinguish fire in sector. Returns True if task finished."""
        if not sector or sector.fire_level <= 0:
            return True
        
        reduction = self._extinguishing_rate * delta
        sector.fire_level = max(0, sector.fire_level - reduction)
        return sector.fire_level <= 0

    def is_task_finished(self, sector: Sector) -> bool:
        return sector.fire_level <= 0
    
    def increment_agents_in_sector(self, sector):
        """No longer used: Map centrally recalculates levels"""
        pass

    def decrement_agents_in_sector(self, sector):
        """No longer used: Map centrally recalculates levels"""
        pass

    @property
    def getId(self):
        return self.fire_brigade_id
    
    @property
    def initial_state(self) -> AGENT_STATE:
        return self._state

    def next(self):
        pass

    def log(self) -> None:
        print(f'Fire brigade {self._fire_brigade_id} is in state: {self._state}.')
        logging.debug(f'Fire brigade {self._fire_brigade_id} is in state: {self._state}.')

    def clone(self) -> 'FireBrigade':
        return FireBrigade(
            fire_brigade_id=self._fire_brigade_id,
            timestamp=self._timestamp, 
            initial_state=self._state,
            base_location=Location(self._base_location.latitude, self._base_location.longitude),
            initial_location=Location(self._initial_location.latitude, self._initial_location.longitude)  # Assuming _initial_location exists
        )
    
    # LLM and communication methods
    def make_llm_decision(
        self,
        available_sectors: List[Sector],
        peer_announcements: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make a decision using LLM based on current state and available sectors.
        
        Args:
            available_sectors: List of sectors with fires
            peer_announcements: Optional list of peer action announcements
            
        Returns:
            Decision dict with 'decision', 'target_sector_id', 'reasoning', 'priority', or None
        """
        if not self._llm_client:
            logger.debug(f"[FireBrigade {self._fire_brigade_id}] LLM client not available")
            return None
        
        try:
            # Prepare current state
            current_state = self._prepare_state_for_llm()
            
            # Prepare available sectors
            available_sectors_dict = self._prepare_sectors_for_llm(available_sectors)
            
            # Prepare peer actions
            peer_actions = []
            if peer_announcements:
                peer_actions = [
                    {
                        "agent_id": ann.get("agent_id"),
                        "action": ann.get("action"),
                        "target_sector_id": ann.get("target_sector_id"),
                        "timestamp": ann.get("timestamp"),
                        "reasoning": ann.get("reasoning")
                    }
                    for ann in peer_announcements
                    if ann.get("agent_id") != self._fire_brigade_id
                ]
            
            # Make decision via LLM
            decision = self._llm_client.make_decision(
                agent_id=str(self._fire_brigade_id),
                current_state=current_state,
                available_sectors=available_sectors_dict,
                peer_actions=peer_actions
            )
            
            # Update current target
            if decision.get("decision") == "move_to" and decision.get("target_sector_id"):
                self._current_target_sector_id = decision.get("target_sector_id")
            
            logger.info(f"[FireBrigade {self._fire_brigade_id}] LLM decision: {decision.get('decision')}, "
                       f"reasoning: {decision.get('reasoning', 'N/A')[:50]}")
            
            return decision
            
        except Exception as e:
            logger.error(f"[FireBrigade {self._fire_brigade_id}] Error making LLM decision: {e}", exc_info=True)
            return None
    
    def announce_action(
        self,
        action: str,
        target_sector_id: Optional[int] = None,
        reasoning: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """
        Announce an action to other agents.
        
        Args:
            action: Type of action ("moving_to", "starting_extinguish", "task_complete", etc.)
            target_sector_id: Sector ID if applicable
            reasoning: Reasoning for the action
            additional_data: Any additional data
        """
        if not self._agent_communication:
            return
        
        location = {
            "latitude": self._location.latitude,
            "longitude": self._location.longitude
        } if self._location else None
        
        self._agent_communication.announce_action(
            agent_id=str(self._fire_brigade_id),
            action=action,
            target_sector_id=target_sector_id,
            location=location,
            reasoning=reasoning,
            additional_data=additional_data
        )
    
    def get_peer_announcements(
        self,
        action_filter: Optional[str] = None,
        max_count: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get recent announcements from peer agents.
        
        Args:
            action_filter: Filter by action type
            max_count: Maximum number of announcements
            
        Returns:
            List of peer announcements
        """
        if not self._agent_communication:
            return []
        
        return self._agent_communication.get_recent_announcements(
            exclude_agent_id=str(self._fire_brigade_id),
            action_filter=action_filter,
            max_count=max_count
        )
    
    def _prepare_state_for_llm(self) -> Dict[str, Any]:
        """Prepare current agent state for LLM."""
        state_name = self._state.name if hasattr(self._state, 'name') else str(self._state)
        
        return {
            "agent_id": str(self._fire_brigade_id),
            "state": state_name,
            "location": {
                "latitude": self._location.latitude if self._location else 0.0,
                "longitude": self._location.longitude if self._location else 0.0
            },
            "base_location": {
                "latitude": self._base_location.latitude,
                "longitude": self._base_location.longitude
            },
            "destination": {
                "latitude": self._destination.latitude if self._destination else self._base_location.latitude,
                "longitude": self._destination.longitude if self._destination else self._base_location.longitude
            },
            "current_target_sector_id": self._current_target_sector_id
        }
    
    def _prepare_sectors_for_llm(self, sectors: List[Sector]) -> List[Dict[str, Any]]:
        """Prepare sectors list for LLM decision-making."""
        available = []
        
        for sector in sectors:
            if sector.fire_level > 0:
                # Calculate distance (simplified)
                if self._location and hasattr(sector, 'center_location'):
                    distance = self._calculate_distance(self._location, sector.center_location)
                else:
                    distance = 0.0
                
                available.append({
                    "sector_id": sector.sector_id,
                    "fire_level": sector.fire_level if hasattr(sector, 'fire_level') else 0.0,
                    "burn_level": sector.burn_level if hasattr(sector, 'burn_level') else 0.0,
                    "location": {
                        "latitude": sector.center_location.latitude if hasattr(sector, 'center_location') else 0.0,
                        "longitude": sector.center_location.longitude if hasattr(sector, 'center_location') else 0.0
                    },
                    "distance_from_agent": distance,
                    "number_of_brigades": sector._number_of_fire_brigades if hasattr(sector, '_number_of_fire_brigades') else 0
                })
        
        # Sort by fire_level / distance ratio
        available.sort(key=lambda s: s["fire_level"] / max(s["distance_from_agent"], 0.001), reverse=True)
        return available[:10]  # Top 10 sectors
    
    def _calculate_distance(self, loc1: Location, loc2: Location) -> float:
        """Calculate distance between two locations."""
        return ((loc1.latitude - loc2.latitude)**2 + 
                (loc1.longitude - loc2.longitude)**2)**0.5
    
    @property
    def llm_client(self):
        """Get LLM client instance."""
        return self._llm_client
    
    @property
    def agent_communication(self):
        """Get agent communication instance."""
        return self._agent_communication