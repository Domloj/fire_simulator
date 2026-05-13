from enum import Enum
from typing import List
from src.engine.models.sensors.sensor_type import SensorType

class TopicRegistry(str, Enum):
    """
    Single source of truth for all RabbitMQ topics in the fire simulation system.
    All topic definitions reference this registry to avoid duplication.
    """
    TEMPERATURE_HUMIDITY = "simulation.telemetry.sensors.temp_humidity"
    WIND_SPEED           = "simulation.telemetry.sensors.wind_speed"
    WIND_DIRECTION       = "simulation.telemetry.sensors.wind_direction"
    LITTER_MOISTURE      = "simulation.telemetry.sensors.litter_moisture"
    CO2                  = "simulation.telemetry.sensors.co2"
    PM2_5                = "simulation.telemetry.sensors.pm2_5"
    CAMERA               = "simulation.telemetry.sensors.camera"
    SECTOR_STATE         = "simulation.telemetry.map.sector_state"
    SECTOR_STATE_FAST    = "simulation.telemetry.map.sector_state_fast"
    FIRE_BRIGADE_STATE   = "simulation.telemetry.agents.fire_brigade"
    FIRE_BRIGADE_STATE_BATCH = "simulation.telemetry.agents.fire_brigade_batch"
    FORESTER_STATE       = "simulation.telemetry.agents.forester"
    FORESTER_STATE_BATCH = "simulation.telemetry.agents.forester_batch"
    FIRE_BRIGADE_ACTIONS = "simulation.control.fire_brigade_actions"
    FORESTER_ACTIONS     = "simulation.control.forester_actions"
    SIMULATION_CONTROL   = "simulation.control.lifecycle"
    EVENTS               = "simulation.events"
    RECOMMENDATIONS      = "simulation.recommendations"
    LLM_REQUESTS         = "support.llm.requests"
    LLM_RESPONSES        = "support.llm.responses"
    LLM_PROPOSITIONS     = "support.llm.propositions"
    ANALYTICS            = "support.analytics.insights"
    TASK_QUEUE           = "backend.tasks.queue"
    DATA_AGGREGATION     = "backend.data.aggregated"
    USER_COMMANDS        = "backend.commands.user"
    AGENT_ANNOUNCEMENTS  = "simulation.agents.announcements" 
    AGENT_COMMUNICATION  = "simulation.agents.communication"

    # Support system topics
    SUPPORT_ANALYSIS_REQUESTS = "support.analysis.requests"
    SUPPORT_RECOMMENDATIONS   = "support.recommendations"
    SUPPORT_AGGREGATED_DATA   = "support.data.aggregated"

class TopicDomain(str, Enum):
    """Top-level domain separation"""
    SIMULATION = "simulation"
    SUPPORT = "support"
    BACKEND = "backend"
    FRONTEND = "frontend"

class SimulationTopics:
    """
    Topics published BY simulator (telemetry).
    References TopicRegistry to avoid duplication.
    """
    SENSORS: List[str] = [
        TopicRegistry.TEMPERATURE_HUMIDITY.value,
        TopicRegistry.WIND_SPEED.value,
        TopicRegistry.WIND_DIRECTION.value,
        TopicRegistry.LITTER_MOISTURE.value,
        TopicRegistry.CO2.value,
        TopicRegistry.PM2_5.value,
        TopicRegistry.CAMERA.value,
    ]
    
    AGENTS: List[str] = [
        TopicRegistry.FIRE_BRIGADE_STATE.value,
        TopicRegistry.FORESTER_STATE.value,
        TopicRegistry.FIRE_BRIGADE_STATE_BATCH.value,
        TopicRegistry.FORESTER_STATE_BATCH.value,
    ]
    
    MAP: List[str] = [
        TopicRegistry.SECTOR_STATE.value,
        TopicRegistry.SECTOR_STATE_FAST.value,
    ]
    
    EVENTS: List[str] = [
        TopicRegistry.EVENTS.value,
    ]
    
    COMMUNICATION: List[str] = [
        TopicRegistry.AGENT_ANNOUNCEMENTS.value,
        TopicRegistry.AGENT_COMMUNICATION.value,
        TopicRegistry.LLM_REQUESTS.value,
        TopicRegistry.LLM_PROPOSITIONS.value,
    ]
    
    ALL: List[str] = SENSORS + AGENTS + MAP + EVENTS + COMMUNICATION

class ControlTopics:
    """
    Topics consumed BY simulator (commands from outside).
    References TopicRegistry to avoid duplication.
    """
    FIRE_BRIGADE = TopicRegistry.FIRE_BRIGADE_ACTIONS.value
    FORESTER = TopicRegistry.FORESTER_ACTIONS.value
    LIFECYCLE = TopicRegistry.SIMULATION_CONTROL.value
    
    ALL: List[str] = [FIRE_BRIGADE, FORESTER, LIFECYCLE]

class SupportTopics:
    """
    Topics for decision support system.
    References TopicRegistry to avoid duplication.
    """
    RECOMMENDATIONS = TopicRegistry.RECOMMENDATIONS.value
    ANALYSIS_REQUESTS = TopicRegistry.SUPPORT_ANALYSIS_REQUESTS.value
    SUPPORT_RECOMMENDATIONS = TopicRegistry.SUPPORT_RECOMMENDATIONS.value
    AGGREGATED_DATA = TopicRegistry.SUPPORT_AGGREGATED_DATA.value
    LLM_REQUESTS = TopicRegistry.LLM_REQUESTS.value
    LLM_RESPONSES = TopicRegistry.LLM_RESPONSES.value
    ANALYTICS = TopicRegistry.ANALYTICS.value
    
    ALL: List[str] = [RECOMMENDATIONS, ANALYSIS_REQUESTS, SUPPORT_RECOMMENDATIONS, AGGREGATED_DATA, LLM_REQUESTS, LLM_RESPONSES, ANALYTICS]

class BackendTopics:
    """
    Backend orchestration topics.
    References TopicRegistry to avoid duplication.
    """
    TASK_QUEUE = TopicRegistry.TASK_QUEUE.value
    DATA_AGGREGATION = TopicRegistry.DATA_AGGREGATION.value
    USER_COMMANDS = TopicRegistry.USER_COMMANDS.value
    
    ALL: List[str] = [TASK_QUEUE, DATA_AGGREGATION, USER_COMMANDS]

def get_all_topics() -> List[str]:
    """Return list of all topic values from TopicRegistry"""
    return [topic.value for topic in TopicRegistry]

ALL_TOPICS = get_all_topics()
SENSOR_TO_TOPIC = {
    SensorType.TEMPERATURE_AND_AIR_HUMIDITY: TopicRegistry.TEMPERATURE_HUMIDITY,
    SensorType.WIND_SPEED:                   TopicRegistry.WIND_SPEED,
    SensorType.WIND_DIRECTION:               TopicRegistry.WIND_DIRECTION,
    SensorType.LITTER_MOISTURE:              TopicRegistry.LITTER_MOISTURE,
    SensorType.CO2:                          TopicRegistry.CO2,
    SensorType.PM2_5:                        TopicRegistry.PM2_5,
    SensorType.CAMERA:                       TopicRegistry.CAMERA,
}

def get_topic_for_sensor(sensor_type: SensorType) -> str:
    topic = SENSOR_TO_TOPIC.get(sensor_type)
    if topic is None:
        raise ValueError(f"No topic mapping for sensor type: {sensor_type}")
    return topic.value

