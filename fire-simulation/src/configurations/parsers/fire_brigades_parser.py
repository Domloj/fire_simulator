
from datetime import datetime
from typing import List, Dict, Any
import logging

from src.engine.models.core.location import Location
from src.engine.models.agents.fire_brigade import FireBrigade
from src.engine.models.agents.fire_brigade_state import FIREBRIGADE_STATE

logger = logging.getLogger(__name__)

def parse_fire_brigades(fire_brigades_json_data: List[Dict[str, Any]]) -> List[FireBrigade]:
    '''
    Parsing fire brigades data from JSON input from selected configuration
    '''

    brigades = []
    fire_brigades_data = fire_brigades_json_data.get('fireBrigades', [])
    
    if not isinstance(fire_brigades_data, list):
        logger.error("'fireBrigades' is missing or is not a list")
        return brigades
    
    for idx, item in enumerate(fire_brigades_data):
        try:
            fire_brigade_id = item["fireBrigadeId"]
            timestamp = datetime.fromisoformat(item["timestamp"]) 
            state = FIREBRIGADE_STATE[item["state"]]
            
            base_location = Location(
                longitude = float(item["baseLocation"]["longitude"]),
                latitude  = float(item["baseLocation"]["latitude"])
            )

            current_location = Location(
                longitude = float(item["currentLocation"]["longitude"]),
                latitude  = float(item["currentLocation"]["latitude"])
            )

            brigades.append(FireBrigade(
                fire_brigade_id  = fire_brigade_id,
                timestamp        = timestamp,
                initial_state    = state,
                base_location    = base_location,
                initial_location = current_location
            ))
       
        except KeyError as e:
            brigade_id = item.get("fireBrigadeId", f"index_{idx}")
            logger.error(f"Resource not found: Missing required field in fire brigade {brigade_id} at index {idx}. Missing key: {e}", exc_info=True)
            continue
        
        except ValueError as e:
            brigade_id = item.get("fireBrigadeId", f"index_{idx}")
            logger.error(f"Invalid data format: Error parsing fire brigade {brigade_id} at index {idx}. Value error: {e}", exc_info=True)
            continue
        
        except TypeError as e:
            brigade_id = item.get("fireBrigadeId", f"index_{idx}")
            logger.error(f"Invalid data format: Error parsing fire brigade {brigade_id} at index {idx}. Type error: {e}", exc_info=True)
            continue
        
    return brigades
