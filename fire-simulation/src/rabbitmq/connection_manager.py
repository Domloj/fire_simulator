import pika
import logging
import time
import threading
from src.settings.communucation_settings import CommunicationSettings

logger = logging.getLogger(__name__)

class RabbitMQConnectionManager:
    def __init__(self, settings: CommunicationSettings):
        self._settings = settings
        self._connection = None
        self._lock = threading.Lock()

    def _create_connection(self) -> pika.BlockingConnection:
        creds = pika.PlainCredentials(
            self._settings.rabbitmq_username, 
            self._settings.rabbitmq_password
        )
        params = pika.ConnectionParameters(
            host                       = self._settings.rabbitmq_host,
            port                       = self._settings.rabbitmq_port,
            credentials                = creds,
            heartbeat                  = 60,
            blocked_connection_timeout = 30,
            retry_delay                = 5, # seconds
            connection_attempts        = 3,
        )
        logger.info(f"Attempting to connect to RabbitMQ at {self._settings.rabbitmq_host}:{self._settings.rabbitmq_port}")
        return pika.BlockingConnection(params)

    def get_connection(self) -> pika.BlockingConnection:
        with self._lock:
            if self._connection is None or self._connection.is_closed:
                for attempt in range(3):
                    try:
                        self._connection = self._create_connection()
                        logger.info("Successfully connected to RabbitMQ.")
                        return self._connection
                    except pika.exceptions.AMQPConnectionError as e:
                        logger.warning(f"RabbitMQ connection attempt {attempt + 1} failed: {e}")
                        time.sleep(5)
                logger.error("Failed to connect to RabbitMQ after multiple attempts.")
                raise pika.exceptions.AMQPConnectionError("Could not establish RabbitMQ connection.")
            return self._connection

    def close_connection(self):
        with self._lock:
            if self._connection and not self._connection.is_closed:
                logger.info("Closing RabbitMQ connection...")
                self._connection.close()
                self._connection = None
                logger.info("RabbitMQ connection closed.")
