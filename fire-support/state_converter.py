"""
State conversion utilities.

Converts between state dictionaries and ForestMap objects for MCTS processing.
"""

import logging
from typing import Dict, Optional

from simulation.forest_map import ForestMap
from simulation.location import Location
from simulation.agent_state import AGENT_STATE

logger = logging.getLogger(__name__)


class StateConverter:    
    @staticmethod
    def state_to_forest_map(
        sectors: Dict[int, Dict],
        fire_brigades: Dict[str, Dict],
        forester_patrols: Dict[str, Dict],
        config: Dict
    ) -> Optional[ForestMap]:
        try:
            if not config or 'location' not in config:
                logger.error("Configuration missing required 'location' field")
                return None
            
            forest_map = ForestMap.from_conf(config)
            
            StateConverter._update_sectors(forest_map, sectors)
            StateConverter._update_fire_brigades(forest_map, fire_brigades)
            StateConverter._update_forester_patrols(forest_map, forester_patrols)
            
            return forest_map
            
        except KeyError as e:
            logger.error(f"Missing required field in config: {e}")
            return None
        except Exception as e:
            logger.error(f"Error converting state to ForestMap: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _update_sectors(forest_map: ForestMap, sectors: Dict[int, Dict]):
        """Update sectors in ForestMap with current state"""
        from simulation.sectors.fire_state import FireState
        
        for row in forest_map.sectors:
            for sector in row:
                if not sector:
                    continue
                
                sector_id = sector.sector_id
                if sector_id not in sectors:
                    continue
                
                sector_state = sectors[sector_id]
                state_obj = sector_state.get('state', {})
                
                if not isinstance(state_obj, dict):
                    logger.warning(f"Sector {sector_id} state is not a dict: {type(state_obj)}")
                    continue
                
                fire_level = state_obj.get('fireLevel', 0)
                burn_level = state_obj.get('burnLevel', 0)
                extinguish_level = state_obj.get('extinguishLevel', 0)
                
                sector._fire_state = FireState.ACTIVE if fire_level > 0 else FireState.INACTIVE
                sector.fire_level = fire_level
                sector.burn_level = burn_level
                sector.extinguish_level = extinguish_level
    
    @staticmethod
    def _update_fire_brigades(forest_map: ForestMap, fire_brigades: Dict[str, Dict]):
        """Update fire brigades in ForestMap with current state"""
        for brigade in forest_map.fireBrigades:
            brigade_id_key = str(brigade.fire_brigade_id)
            if brigade_id_key not in fire_brigades:
                continue
            
            brigade_state = fire_brigades[brigade_id_key]
            location = brigade_state.get('location', {})

            if location and isinstance(location, dict):
                try:
                    brigade._location = Location(
                        latitude=location.get('latitude', 0),
                        longitude=location.get('longitude', 0)
                    )
                except Exception as e:
                    logger.warning(f"Error updating brigade {brigade_id_key} location: {e}")
            
            state_name = brigade_state.get('state')
            if state_name:
                state_mapping = {
                    'AVAILABLE': AGENT_STATE.AVAILABLE,
                    'TRAVELLING': AGENT_STATE.TRAVELLING,
                    'EXTINGUISHING': AGENT_STATE.EXECUTING,
                }
                mapped_state = state_mapping.get(state_name)
                if mapped_state:
                    brigade._state = mapped_state
                else:
                    logger.warning(f"Unknown fire brigade state: {state_name}")
            else:
                brigade._state = AGENT_STATE.AVAILABLE
    
    @staticmethod
    def _update_forester_patrols(forest_map: ForestMap, forester_patrols: Dict[str, Dict]):
        """Update forester patrols in ForestMap with current state"""
        for patrol in forest_map.foresterPatrols:
            patrol_id_key = str(patrol.forester_patrol_id)
            if patrol_id_key not in forester_patrols:
                continue
            
            patrol_state = forester_patrols[patrol_id_key]
            
            location = patrol_state.get('location', {})
            if location and isinstance(location, dict):
                try:
                    patrol._location = Location(
                        latitude=location.get('latitude', 0),
                        longitude=location.get('longitude', 0)
                    )
                except Exception as e:
                    logger.warning(f"Error updating patrol {patrol_id_key} location: {e}")
            
            state_name = patrol_state.get('state')
            if state_name:
                state_mapping = {
                    'AVAILABLE': AGENT_STATE.AVAILABLE,
                    'TRAVELLING': AGENT_STATE.TRAVELLING,
                    'PATROLLING': AGENT_STATE.EXECUTING,
                }
                mapped_state = state_mapping.get(state_name)
                if mapped_state:
                    patrol._state = mapped_state
                else:
                    logger.warning(f"Unknown forester patrol state: {state_name}")
            else:
                patrol._state = AGENT_STATE.AVAILABLE