import os
from pydantic import Field
from pydantic_settings import BaseSettings
from src.messaging.topics import ControlTopics, SimulationTopics

DEFAULT_RABBITMQ_HOST = "rabbitmq"
DEFAULT_RABBITMQ_PORT = 5672
DEFAULT_RABBITMQ_USER = "guest"
DEFAULT_RABBITMQ_PASS = "guest"
DEFAULT_EXCHANGE      = "fire-simulation-exchange"

class CommunicationSettings(BaseSettings):
    rabbitmq_host: str           = Field(DEFAULT_RABBITMQ_HOST, env="RABBITMQ_HOST")
    rabbitmq_port: int           = Field(DEFAULT_RABBITMQ_PORT, env="RABBITMQ_PORT")
    rabbitmq_username: str       = Field(DEFAULT_RABBITMQ_USER, env="RABBITMQ_USERNAME")
    rabbitmq_password: str       = Field(DEFAULT_RABBITMQ_PASS, env="RABBITMQ_PASSWORD")
    exchange_name: str           = Field(DEFAULT_EXCHANGE,      env="FIRE_SIMULATION_EXCHANGE_NAME")
    published_topics: list[str]  = Field(default_factory=list)
    subscribed_topics: list[str] = Field(default_factory=list)

class SimulatorCommunicationSettings(CommunicationSettings):
    published_topics: list[str] = Field(default_factory=lambda: SimulationTopics.ALL)
    subscribed_topics: list[str] = Field(default_factory=lambda: ControlTopics.ALL)

def get_communication_settings() -> CommunicationSettings:
    return CommunicationSettings()

def get_simulator_settings() -> SimulatorCommunicationSettings:
    return SimulatorCommunicationSettings()
