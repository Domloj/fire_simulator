"""
Agent Type Configuration - eliminates conditional logic and code duplication.

This module provides a configuration-driven approach for handling different agent types.
Instead of using isinstance() checks throughout the codebase, each agent type is
configured once with its specific parameters (ID fields, topics, display names).

Usage:
    from agent_type_config import get_agent_config, AGENT_CONFIGS
    
    # Get config for agent instance
    config = get_agent_config(my_agent)
    topic = config.telemetry_topic
    
    # Get config by type name
    config = get_config_by_type_name("fire_brigade")
"""

from dataclasses import dataclass
from typing import Dict
from src.messaging.topics import TopicRegistry

@dataclass(frozen=True)
class AgentTypeConfig:
    """
    Configuration for specific agent type.
    
    This eliminates the need for conditional logic (isinstance checks) when handling
    different agent types. Adding a new agent type requires only adding a configuration,
    not modifying multiple methods across different classes.
    
    Attributes:
        type_name: Type identifier for telemetry messages ("fire_brigade", "forester")
        id_field_name: Field name for agent ID in messages ("fireBrigadeId", "foresterPatrolId")
        display_name: Human-readable name for logging ("FireBrigade", "ForesterPatrol")
        telemetry_topic: RabbitMQ topic for publishing agent state
        command_topic: RabbitMQ topic for receiving commands
    """
    type_name: str
    id_field_name: str
    display_name: str
    telemetry_topic: str
    command_topic: str


# Registry of agent type configurations
# Adding a new agent type: just add a configuration here
AGENT_CONFIGS: Dict[str, AgentTypeConfig] = {
    "fire_brigade": AgentTypeConfig(
        type_name="fire_brigade",
        id_field_name="fireBrigadeId",
        display_name="FireBrigade",
        telemetry_topic=TopicRegistry.FIRE_BRIGADE_STATE.value,
        command_topic=TopicRegistry.FIRE_BRIGADE_ACTIONS.value
    ),
    "forester": AgentTypeConfig(
        type_name="forester",
        id_field_name="foresterPatrolId",
        display_name="ForesterPatrol",
        telemetry_topic=TopicRegistry.FORESTER_STATE.value,
        command_topic=TopicRegistry.FORESTER_ACTIONS.value
    )
}


def get_agent_config(agent) -> AgentTypeConfig:
    """
    Get configuration for given agent instance.
    
    This function performs the isinstance check ONCE here, rather than
    repeating it throughout the codebase.
    
    Args:
        agent: Agent instance (FireBrigade or ForesterPatrol)
        
    Returns:
        AgentTypeConfig for the agent's type
        
    Raises:
        ValueError: If agent type is not recognized
        
    Example:
        >>> config = get_agent_config(my_fire_brigade)
        >>> print(config.telemetry_topic)
        'simulation.telemetry.agents.fire_brigade'
    """
    # Import here to avoid circular dependency
    from src.engine.models.agents.fire_brigade import FireBrigade
    from src.engine.models.agents.forester_patrol import ForesterPatrol
    
    if isinstance(agent, FireBrigade):
        return AGENT_CONFIGS["fire_brigade"]
    elif isinstance(agent, ForesterPatrol):
        return AGENT_CONFIGS["forester"]
    else:
        raise ValueError(f"Unknown agent type: {type(agent).__name__}")


def get_config_by_type_name(type_name: str) -> AgentTypeConfig:
    """
    Get configuration by type name string.
    
    Args:
        type_name: Type identifier ("fire_brigade" or "forester")
        
    Returns:
        AgentTypeConfig for the specified type
        
    Raises:
        ValueError: If type_name is not recognized
        
    Example:
        >>> config = get_config_by_type_name("fire_brigade")
        >>> print(config.id_field_name)
        'fireBrigadeId'
    """
    config = AGENT_CONFIGS.get(type_name)
    if config is None:
        available = list(AGENT_CONFIGS.keys())
        raise ValueError(f"Unknown agent type name: {type_name}. Available: {available}")
    return config


def get_config_by_id_field(id_field_name: str) -> AgentTypeConfig:
    """
    Get configuration by ID field name (useful for parsing messages).
    
    Args:
        id_field_name: Field name in message ("fireBrigadeId" or "foresterPatrolId")
        
    Returns:
        AgentTypeConfig for the agent type with that ID field
        
    Raises:
        ValueError: If no configuration matches the ID field name
        
    Example:
        >>> config = get_config_by_id_field("fireBrigadeId")
        >>> print(config.type_name)
        'fire_brigade'
    """
    for config in AGENT_CONFIGS.values():
        if config.id_field_name == id_field_name:
            return config
    
    available = [c.id_field_name for c in AGENT_CONFIGS.values()]
    raise ValueError(f"Unknown ID field name: {id_field_name}. Available: {available}")


def get_all_agent_configs() -> list[AgentTypeConfig]:
    """
    Get list of all registered agent configurations.
    
    Returns:
        List of all AgentTypeConfig instances
        
    Example:
        >>> configs = get_all_agent_configs()
        >>> for config in configs:
        ...     print(f"{config.display_name}: {config.command_topic}")
    """
    return list(AGENT_CONFIGS.values())
