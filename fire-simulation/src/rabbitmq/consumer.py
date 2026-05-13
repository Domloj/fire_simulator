import logging
import json
import pika
import time
from src.rabbitmq.message_store import MessageStore

logger = logging.getLogger(__name__)

def consume_messages_from_queue(queue_name, store: MessageStore, username, password, stop_event, host="127.0.0.1", port=5672):
    """
    Background thread function to consume messages from RabbitMQ and put into MessageStore.
    """
    connection = None
    channel = None
    
    while not stop_event.is_set():
        try:
            if not connection or connection.is_closed:
                credentials = pika.PlainCredentials(username, password)

                parameters = pika.ConnectionParameters(
                    host                       = host, 
                    port                       = port, 
                    credentials                = credentials,
                    heartbeat                  = 60, 
                    blocked_connection_timeout = 30
                )
                connection = pika.BlockingConnection(parameters)
                channel = connection.channel()
                logger.info(f"Consumer thread for {queue_name} connected")

            method_frame, header_frame, body = channel.basic_get(queue=queue_name, auto_ack=True)
            if method_frame:
                message = json.loads(body)
                store.add_received_message(message, queue_name)
            
            # Reduced frequency to prevent message queue hammering
            time.sleep(1.0)
            
        except Exception as e:
            logger.error(f"Error in consumer thread for {queue_name}: {e}")
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
            # Connection may already be closed or lost - this is expected during shutdown
            logger.debug(f"Error closing connection on thread exit (expected during shutdown): {e}")
    
    logger.info(f"Consumer thread for {queue_name} stopped")
