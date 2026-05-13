from datetime import datetime

from src.engine.models.agents.agent import Agent
from src.engine.models.agents.fire_brigade import FireBrigade
from src.engine.models.agents.fire_brigade_state import FIREBRIGADE_STATE
from src.engine.models.agents.forest_patrols_state import FORESTERPATROL_STATE
from src.engine.models.agents.forester_patrol import ForesterPatrol
from src.engine.models.map.sector import Sector


def generate_traveling_message(agent: Agent, sector: Sector = None):
    if isinstance(agent, FireBrigade):
        message = {
            "fireBrigadeId": agent.fire_brigade_id,
            "state": FIREBRIGADE_STATE.TRAVELLING.name,
            "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude": agent.location.longitude,
                "latitude": agent.location.latitude
            }
        }
        if sector is not None:
            message["sectorId"] = sector.sector_id
        return message
    
    elif isinstance(agent, ForesterPatrol):
        message = {
            "foresterPatrolId": agent.forester_patrol_id,
            "state": FORESTERPATROL_STATE.TRAVELLING.name,
            "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude": agent.location.longitude,
                "latitude": agent.location.latitude
            }
        }
        if sector is not None:
            message["sectorId"] = sector.sector_id
        return message

def generate_message_available(agent : Agent, sector: Sector = None):
    if isinstance(agent, FireBrigade):
        message = {
            "fireBrigadeId": agent.fire_brigade_id,
            "state": FIREBRIGADE_STATE.AVAILABLE.name,
            "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude": agent.location.longitude,
                "latitude": agent.location.latitude
            }
        }
        if sector is not None:
            message["sectorId"] = sector.sector_id
        return message
    
    elif isinstance(agent, ForesterPatrol):
        message = {
            "foresterPatrolId" : agent.forester_patrol_id,
            "state" : FORESTERPATROL_STATE.AVAILABLE.name,
            "timestamp" : datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude" : agent.location.longitude,
                "latitude" : agent.location.latitude
            }
        }
        if sector is not None:
            message["sectorId"] = sector.sector_id
        return message
    
def generate_message_extinguished(agent : Agent, sector: Sector):
    if isinstance(agent, FireBrigade):
        return  {
            "fireBrigadeId": agent.fire_brigade_id,
            "state": FIREBRIGADE_STATE.AVAILABLE.name,
            "fireState": sector.fire_state.name,
            "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude" : agent.location.longitude,
                "latitude" : agent.location.latitude
            },
            "sectorId": sector.sector_id
        }
    
def generate_message_extinguishing(agent : Agent, sector: Sector = None):
    if isinstance(agent, FireBrigade):
        message = {
            "fireBrigadeId": agent.fire_brigade_id,
            "state": FIREBRIGADE_STATE.EXTINGUISHING.name,
            "timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude" : agent.location.longitude,
                "latitude" : agent.location.latitude
            }
        }
        if sector is not None:
            message["sectorId"] = sector.sector_id
        return message

def generate_message_patrolling(agent : Agent, sector : Sector):
    if isinstance(agent, ForesterPatrol):
        return {
            "foresterPatrolId" : agent.forester_patrol_id,
            "state" : FORESTERPATROL_STATE.PATROLLING.name,
            "timestamp" : datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
            "location": {
                "longitude" : agent.location.longitude,
                "latitude" : agent.location.latitude
            },
            "sectorState": sector.fire_state.name
        }