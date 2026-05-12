"""
State management module for tracking simulation state.

Handles thread-safe state updates and retrieval for sectors, fire brigades,
and forester patrols.
"""

import logging
import threading
import time
from typing import Dict, Optional, Tuple, Union

from contracts import (
    SectorStateUpdate,
    FireBrigadeStateUpdate,
    ForesterPatrolStateUpdate,
    extract_minimal_sector_update,
    extract_minimal_brigade_update,
    extract_minimal_patrol_update
)

logger = logging.getLogger(__name__)


class StateManager:
    """Thread-safe state manager for simulation entities"""
    
    def __init__(self):
        self.sectors: Dict[int, Dict] = {}
        self.fire_brigades: Dict[str, Dict] = {}     # Key as string for consistency
        self.forester_patrols: Dict[str, Dict] = {}  # Key as string for consistency
        self.lock = threading.RLock()                # Reentrant lock for nested calls
        self.last_update_time = time.time()
        self.config: Optional[Dict] = None
        self.forest_id: Optional[str] = None
        self.simulation_session_id: Optional[str] = None
    
    def update_sector_state(self, sector_state: Dict) -> bool:
        """
        Update sector state from message.
        
        Returns:
            True if updated, False if sector_id missing or wrong forest_id
        """
        msg_forest_id = sector_state.get('forestId')
        msg_session_id = sector_state.get('simulationSessionId')
        
        if self.simulation_session_id:
            if not msg_session_id:
                logger.debug(f"Ignoring sector update missing simulationSessionId (active: {self.simulation_session_id})")
                return False
            if msg_session_id != self.simulation_session_id:
                logger.debug(f"Ignoring sector update for old simulationSessionId: {msg_session_id} (active: {self.simulation_session_id})")
                return False
            
        if msg_forest_id and self.forest_id and msg_forest_id != self.forest_id:
            logger.debug(f"Ignoring sector update for old forestId: {msg_forest_id}")
            return False

        sector_id = sector_state.get('sectorId')
        if sector_id is None:
            logger.warning(f"Sector state missing sectorId: {sector_state.keys()}")
            return False
        
        try:
            sector_id = int(sector_id)
        except (ValueError, TypeError):
            logger.error(f"Invalid sectorId type: {type(sector_id)}, value: {sector_id}")
            return False
        
        with self.lock:
            existing = self.sectors.get(sector_id, {})
            minimal_update = extract_minimal_sector_update(sector_state)
            
            for key in ['row', 'column', 'sectorType']:
                if key in existing and key not in minimal_update:
                    minimal_update[key] = existing[key]
                elif key in sector_state:
                    minimal_update[key] = sector_state[key]
            
            self.sectors[sector_id] = minimal_update
            self.last_update_time = time.time()
            
            state_obj = sector_state.get('state', {})
            fire_level = state_obj.get('fireLevel', 0) if isinstance(state_obj, dict) else 0
            logger.debug(f"Updated sector {sector_id}: fireLevel={fire_level}")
        
        return True
    
    def update_fire_brigade_state(self, brigade_state: Dict) -> bool:
        """
        Update fire brigade state from message.
        
        Returns:
            True if updated, False if brigade_id missing or wrong forest_id
        """
        msg_forest_id = brigade_state.get('forestId')
        msg_session_id = brigade_state.get('simulationSessionId')
        
        if self.simulation_session_id:
            if not msg_session_id:
                logger.debug(f"Ignoring brigade update missing simulationSessionId (active: {self.simulation_session_id})")
                return False
            if msg_session_id != self.simulation_session_id:
                logger.debug(f"Ignoring brigade update for old simulationSessionId: {msg_session_id} (active: {self.simulation_session_id})")
                return False
            
        if msg_forest_id and self.forest_id and msg_forest_id != self.forest_id:
            logger.debug(f"Ignoring brigade update for old forestId: {msg_forest_id}")
            return False

        brigade_id = None
        if 'fireBrigadeId' in brigade_state:
            brigade_id = brigade_state['fireBrigadeId']
        elif 'id' in brigade_state:
            brigade_id = brigade_state['id']
        
        if brigade_id is None:
            logger.warning(f"Fire brigade state missing ID: {brigade_state.keys()}")
            return False
        
        try:
            brigade_id_str = str(brigade_id)
            if not brigade_id_str.strip() and brigade_id != 0:
                logger.warning(f"Fire brigade state has empty ID: {brigade_state.keys()}")
                return False
        except Exception as e:
            logger.warning(f"Fire brigade state has invalid ID type: {type(brigade_id)}, error: {e}")
            return False
        
        with self.lock:
            minimal_update = extract_minimal_brigade_update(brigade_state)
            if 'location' in minimal_update:
                minimal_update['location'] = self.fire_brigades.get(brigade_id_str, {}).get('location', {})
            self.fire_brigades[brigade_id_str] = minimal_update
            self.last_update_time = time.time()
            logger.debug(f"Updated fire brigade {brigade_id_str}: state={brigade_state.get('state')} (location not updated)")
        
        return True
    
    def update_forester_patrol_state(self, patrol_state: Dict) -> bool:
        """
        Update forester patrol state from message.
        
        Returns:
            True if updated, False if patrol_id missing or wrong forest_id
        """
        msg_forest_id = patrol_state.get('forestId')
        msg_session_id = patrol_state.get('simulationSessionId')
        
        if self.simulation_session_id:
            if not msg_session_id:
                logger.debug(f"Ignoring patrol update missing simulationSessionId (active: {self.simulation_session_id})")
                return False
            if msg_session_id != self.simulation_session_id:
                logger.debug(f"Ignoring patrol update for old simulationSessionId: {msg_session_id} (active: {self.simulation_session_id})")
                return False
            
        if msg_forest_id and self.forest_id and msg_forest_id != self.forest_id:
            logger.debug(f"Ignoring patrol update for old forestId: {msg_forest_id}")
            return False

        patrol_id = None
        if 'foresterPatrolId' in patrol_state:
            patrol_id = patrol_state['foresterPatrolId']
        elif 'id' in patrol_state:
            patrol_id = patrol_state['id']
        
        if patrol_id is None:
            logger.warning(f"Forester patrol state missing ID: {patrol_state.keys()}")
            return False
        
        try:
            patrol_id_str = str(patrol_id)
            if not patrol_id_str.strip() and patrol_id != 0:
                logger.warning(f"Forester patrol state has empty ID: {patrol_state.keys()}")
                return False
        except Exception as e:
            logger.warning(f"Forester patrol state has invalid ID type: {type(patrol_id)}, error: {e}")
            return False
        
        with self.lock:
            minimal_update = extract_minimal_patrol_update(patrol_state)
            if 'location' in minimal_update:
                minimal_update['location'] = self.forester_patrols.get(patrol_id_str, {}).get('location', {})
            self.forester_patrols[patrol_id_str] = minimal_update
            self.last_update_time = time.time()
            logger.debug(f"Updated forester patrol {patrol_id_str}: state={patrol_state.get('state')} (location not updated)")
        
        return True

    def update_agent_position(self, agent_position: Dict) -> bool:
        agent_id = agent_position.get('id')
        unit_type = agent_position.get('unitType')
        if agent_id is None or unit_type not in ['fireBrigade', 'foresterPatrol']:
            logger.warning(f"Invalid agent_position event: {agent_position}")
            return False
        agent_id_str = str(agent_id)
        with self.lock:
            if unit_type == 'fireBrigade':
                if agent_id_str not in self.fire_brigades:
                    self.fire_brigades[agent_id_str] = {'state': None}
                self.fire_brigades[agent_id_str]['location'] = {
                    'latitude': agent_position.get('latitude'),
                    'longitude': agent_position.get('longitude'),
                    'timestamp': agent_position.get('timestamp')
                }
                logger.debug(f"Updated fire brigade {agent_id_str} position: {self.fire_brigades[agent_id_str]['location']}")
            elif unit_type == 'foresterPatrol':
                if agent_id_str not in self.forester_patrols:
                    self.forester_patrols[agent_id_str] = {'state': None}
                self.forester_patrols[agent_id_str]['location'] = {
                    'latitude': agent_position.get('latitude'),
                    'longitude': agent_position.get('longitude'),
                    'timestamp': agent_position.get('timestamp')
                }
                logger.debug(f"Updated forester patrol {agent_id_str} position: {self.forester_patrols[agent_id_str]['location']}")
        return True
    
    def get_state_copy(self) -> Tuple[Dict[int, Dict], Dict[str, Dict], Dict[str, Dict]]:
        """Get a thread-safe copy of current state"""
        with self.lock:
            return (
                dict(self.sectors),
                dict(self.fire_brigades),
                dict(self.forester_patrols)
            )
    
    def set_config(self, config: Dict) -> None:
        """Set forest configuration"""
        if not config:
            logger.warning("Attempted to set empty config")
            return
        
        with self.lock:
            self.config = config
            self.forest_id = config.get('forestId')
            self.simulation_session_id = config.get('simulationSessionId')
            logger.info(f"Configuration updated for forestId: {self.forest_id}, sessionId: {self.simulation_session_id}")
    
    def get_config(self) -> Optional[Dict]:
        """Get forest configuration"""
        with self.lock:
            return self.config
    
    def get_sector(self, sector_id: int) -> Optional[Dict]:
        """Get specific sector state"""
        with self.lock:
            return self.sectors.get(sector_id)
    
    def get_fire_brigade(self, brigade_id: Union[int, str]) -> Optional[Dict]:
        """Get specific fire brigade state"""
        with self.lock:
            brigade_id_str = str(brigade_id)
            return self.fire_brigades.get(brigade_id_str)
    
    def get_forester_patrol(self, patrol_id: Union[int, str]) -> Optional[Dict]:
        """Get specific forester patrol state"""
        with self.lock:
            patrol_id_str = str(patrol_id)
            return self.forester_patrols.get(patrol_id_str)
    
    def clear_state(self) -> None:
        """Clear all simulation entity states (but keep config if desired)"""
        with self.lock:
            self.sectors.clear()
            self.fire_brigades.clear()
            self.forester_patrols.clear()
            self.last_update_time = time.time()
            logger.info("StateManager: Cleared all simulation entity states")