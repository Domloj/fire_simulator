"""
Messaging module for FFSim — RabbitMQ integration and telemetry publishing.

Implements spec section 5.2 (telemetry) and enables communication with fire-backend.
"""

from src.messaging.rabbitmq_publisher import RabbitMQPublisher

__all__ = ["RabbitMQPublisher"]
