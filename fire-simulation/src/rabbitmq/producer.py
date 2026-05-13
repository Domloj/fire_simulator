import pika
import logging
import json
import time
from src.rabbitmq.connection_manager import RabbitMQConnectionManager
from src.settings.communucation_settings import CommunicationSettings
from src.rabbitmq.message_store import MessageStore

logger = logging.getLogger(__name__)

class RabbitMQProducer:
    def __init__(self, settings: CommunicationSettings):
        self._settings = settings
        self._connection_manager = RabbitMQConnectionManager(settings)
        self._channel = None
        self._connection = None
        self._connect()

    def _connect(self):
        try:
            self._connection = self._connection_manager.get_connection()
            self._channel = self._connection.channel()

            self._channel.exchange_declare(
                exchange      = self._settings.exchange_name, 
                exchange_type ='topic', 
                durable       = False
            )
            logger.info(f"Producer connected to RabbitMQ and declared exchange: {self._settings.exchange_name}")
        except Exception as e:
            logger.error(f"Failed to connect producer to RabbitMQ: {e}")
            self._channel = None
            self._connection = None

    def publish_message(self, routing_key: str, message: dict):
        if not self._channel or self._connection.is_closed:
            logger.warning("Producer channel or connection is closed, attempting to reconnect...")
            self._connect()
            if not self._channel:
                logger.error("Failed to reconnect producer, message not sent.")
                return
        try:
            self._channel.basic_publish(
                exchange    = self._settings.exchange_name,
                routing_key = routing_key,
                body        = json.dumps(message),
                properties  = pika.BasicProperties(delivery_mode=1) 
            )
            logger.debug(f"Published message to {routing_key}")
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"AMQP connection error while publishing: {e}. Attempting to reconnect.")
            self._connect()
        except Exception as e:
            logger.error(f"Error publishing message to {routing_key}: {e}")

    async def close(self):
        if self._connection and not self._connection.is_closed:
            logger.info("Closing RabbitMQ producer connection...")
            self._connection.close()
            self._connection = None
            self._channel = None
            logger.info("RabbitMQ producer connection closed.")

def start_producing_messages(exchange, routing_key, store: MessageStore, username, password, stop_event, host="127.0.0.1", port=5672):
    """
    Background thread function to pull messages from MessageStore and send to RabbitMQ.
    """
    connection = None
    channel = None
    
    while not stop_event.is_set():
        try:
            if not connection or connection.is_closed:
                credentials = pika.PlainCredentials(username, password)
                parameters = pika.ConnectionParameters(
                    host=host, port=port, credentials=credentials,
                    heartbeat=60, blocked_connection_timeout=30
                )
                connection = pika.BlockingConnection(parameters)
                channel = connection.channel()
                channel.exchange_declare(exchange=exchange, exchange_type='topic', durable=False)
                logger.info(f"Producer thread for {routing_key} connected")

            # Check for messages to send
            messages = store.get_all_sent_messages(routing_key)
            if messages:
                # Reduce logging for LLM queues to half (only log every other batch)
                is_llm_queue = 'llm' in routing_key.lower()
                log_batch = not (hasattr(start_producing_messages, f'_last_logged_{routing_key}') and getattr(start_producing_messages, f'_last_logged_{routing_key}', False))
                
                if not is_llm_queue or log_batch:
                    logger.info(f"[PRODUCER] Publishing {len(messages)} message(s) to {routing_key}")
                else:
                    logger.debug(f"[PRODUCER] Publishing {len(messages)} message(s) to {routing_key}")
                
                for msg in messages:
                    channel.basic_publish(
                        exchange    = exchange,
                        routing_key = routing_key,
                        body        = json.dumps(msg),
                        properties  = pika.BasicProperties(delivery_mode=1)
                    )
                
                # Toggle logging state for LLM queues
                if is_llm_queue:
                    setattr(start_producing_messages, f'_last_logged_{routing_key}', not getattr(start_producing_messages, f'_last_logged_{routing_key}', False))
                
                store.clear_sent_messages(routing_key)
            
            # Reduced frequency to prevent message queue hammering
            time.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error in producer thread for {routing_key}: {e}")
            if connection and not connection.is_closed:
                try: 
                    connection.close()
                except Exception as close_error:
                    logger.debug(f"Error closing connection in exception handler: {close_error}")
            connection = None
            time.sleep(2)

    # Safely close connection on thread exit
    if connection:
        try:
            if not connection.is_closed:
                connection.close()
        except Exception as e:
            logger.debug(f"Error closing connection on thread exit (expected during shutdown): {e}")
    
    logger.info(f"Producer thread for {routing_key} stopped")
