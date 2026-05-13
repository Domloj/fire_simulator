
from datetime import datetime
from tkinter import E
from typing import List, Dict, Any
import logging
from uu import Error

from src.engine.models.map.fire_state import FireState
from src.engine.models.map.geographic_direction import GeographicDirection
from src.engine.models.map.sector import Sector
from src.engine.models.map.sector_state import SectorState
from src.engine.models.map.sector_type import SectorType

logger = logging.getLogger(__name__)

def parse_sector_state(data: List[Dict[str, Any]]) -> List[Sector]:
    '''
    Parsing sector state data from JSON input from selected configuration
    
    :param data: json input containing sector state information
    :type data: List[Dict[str, Any]]
    :return: list of Sector objects parsed from the input data
    :rtype: List[Sector]
    '''

    sectors = []
    try:
        sector_list = data["sectors"]
        
    except Exception as e:
        logger.error(f"Resource not found: Missing key 'sectors' in sector data. Error: {e}", exc_info=True)
        return sectors

    for idx, val in enumerate(sector_list):
        try:
            direction      = GeographicDirection[val["initialState"]["windDirection"]]
            tmp_sector_id  = val["sectorId"]
            tmp_row        = val["row"] - 1
            tmp_column     = val["column"] - 1

            initial_state = SectorState(
                temperature           = val["initialState"]["temperature"],
                wind_speed            = val["initialState"]["windSpeed"],
                wind_direction        = direction,
                air_humidity          = val["initialState"]["airHumidity"],
                plant_litter_moisture = val["initialState"]["plantLitterMoisture"],
                co2_concentration     = val["initialState"]["co2Concentration"],
                pm2_5_concentration   = val["initialState"]["pm2_5Concentration"],
            )

            sector = Sector(
                sector_id       = tmp_sector_id,
                row             = tmp_row,
                column          = tmp_column,
                sector_type     = SectorType[val["sectorType"]],
                initial_state   = initial_state,
                fire_level      = val["initialState"]["fireLevel"],
                fire_state      = FireState.ACTIVE if (val["initialState"]["fireLevel"] > 0) else FireState.INACTIVE
            )
            sectors.append(sector)
            
        except Exception as e:
            sector_id = val.get("sectorId", f"index_{idx}")
            logger.error(f"Resource not found: Missing required field in sector {sector_id} at index {idx}. Missing key: {e}", exc_info=True)
            continue

    return sectors