"""
RabbitMQ connection and message handling module.

Handles all RabbitMQ operations including:
- Consumer connections for state updates
- Publisher connections for recommendations
- Connection pooling and error recovery
"""

import json
import logging
import os
import pika
import pika.exceptions
import threading
import time
from typing import Callable, Dict, Optional, Any, List

from contracts import validate_state_update, validate_recommendation_message

logger = logging.getLogger(__name__)


class RabbitMQHandler:
    """Handles RabbitMQ connections and message operations"""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        exchange_name: Optional[str] = None
    ):
        self._host = host or os.environ.get('RABBITMQ_HOST', 'rabbitmq-service')
        self._port = port or int(os.environ.get('RABBITMQ_PORT', 5672))
        self._username = username or os.environ.get('RABBITMQ_USER', 'guest')
        self._password = password or os.environ.get('RABBITMQ_PASS', 'guest')
        # Use FIRE_SIMULATION_EXCHANGE_NAME to match simulation service
        self._exchange_name = exchange_name or os.environ.get('RABBITMQ_EXCHANGE') or os.environ.get('FIRE_SIMULATION_EXCHANGE_NAME', 'fire_updates')
        
        self._publisher_connection: Optional[pika.BlockingConnection] = None
        self._publisher_channel: Optional[pika.channel.Channel] = None
        self._publisher_lock = threading.Lock()
        self._publisher_reconnect_delay = 5.0
        
        # Message batching for improved throughput
        self._message_batch: List[Dict] = []
        self._batch_lock = threading.Lock()
        self._batch_size = 10  # Batch up to 10 messages
        self._batch_timeout = 0.1  # 100ms timeout for batching
        
        self._stop_event = threading.Event()
    
    def create_connection(self) -> pika.BlockingConnection:
        """Create a new RabbitMQ connection"""
        credentials = pika.PlainCredentials(self._username, self._password)
        parameters = pika.ConnectionParameters(
            host=self._host,
            port=self._port,
            credentials=credentials,
            connection_attempts=3,
            retry_delay=2
        )
        return pika.BlockingConnection(parameters)
    
    def ensure_publisher_connection(self) -> bool:
        """Ensure publisher connection is active, reconnect if needed"""
        with self._publisher_lock:
            try:
                if self._publisher_connection and not self._publisher_connection.is_closed:
                    if self._publisher_channel and not self._publisher_channel.is_closed:
                        return True
                
                # Need to reconnect
                logger.info("Reconnecting RabbitMQ publisher...")
                self._close_publisher()
                
                self._publisher_connection = self.create_connection()
                self._publisher_channel = self._publisher_connection.channel()
                
                # Declare exchange and queue
                self._publisher_channel.exchange_declare(
                    exchange=self._exchange_name,
                    exchange_type='topic',
                    durable=False
                )
                
                recommendations_queue = 'support_recommendations'
                self._publisher_channel.queue_declare(
                    queue=recommendations_queue,
                    durable=False
                )
                self._publisher_channel.queue_bind(
                    exchange=self._exchange_name,
                    queue=recommendations_queue,
                    routing_key='support.recommendations'
                )
                
                logger.info("RabbitMQ publisher reconnected successfully")
                return True
                
            except pika.exceptions.AMQPConnectionError as e:
                logger.error(f"Failed to connect to RabbitMQ: {e}")
                return False
            except pika.exceptions.ChannelClosedByBroker as e:
                logger.error(f"RabbitMQ channel closed by broker: {e}")
                # Log 404 errors specifically
                if "404" in str(e) or "NOT_FOUND" in str(e):
                    logger.error(f"Resource not found error (404): Exchange '{self._exchange_name}' may not exist. "
                               f"Check RabbitMQ configuration.")
                return False
            except Exception as e:
                logger.error(f"Unexpected error ensuring publisher connection: {e}", exc_info=True)
                return False
    
    def _close_publisher(self):
        """Close publisher connection safely"""
        try:
            if self._publisher_channel and not self._publisher_channel.is_closed:
                self._publisher_channel.close()
        except (pika.exceptions.ConnectionClosed, pika.exceptions.ChannelClosed, ConnectionResetError, IndexError) as e:
            logger.debug(f"Expected error closing publisher channel (connection already closed): {e}")
        except Exception as e:
            logger.debug(f"Error closing publisher channel: {e}")
        
        try:
            if self._publisher_connection and not self._publisher_connection.is_closed:
                self._publisher_connection.close()
        except (pika.exceptions.ConnectionClosed, ConnectionResetError, IndexError) as e:
            logger.debug(f"Expected error closing publisher connection (connection already closed): {e}")
        except Exception as e:
            logger.debug(f"Error closing publisher connection: {e}")
    
    def publish_message(self, message: Dict, routing_key: str, validate: bool = False) -> bool:
        """
        Generic method to publish any message to RabbitMQ.
        
        Args:
            message: Message dict to publish
            routing_key: Routing key for the message
            validate: If True, validates message structure (default: False)
        
        Returns:
            True if published successfully, False otherwise
        """
        if validate and not validate_recommendation_message(message):
            logger.error("Invalid message structure")
            return False
        
        # Immediate publish
        if not self.ensure_publisher_connection():
            logger.error("Cannot publish: publisher connection not available")
            return False
        
        try:
            with self._publisher_lock:
                if not self._publisher_channel or self._publisher_channel.is_closed:
                    logger.warning("Publisher channel not available")
                    return False
                
                self._publisher_channel.basic_publish(
                    exchange=self._exchange_name,
                    routing_key=routing_key,
                    body=json.dumps(message),
                    properties=pika.BasicProperties(
                        delivery_mode=1  # Non-persistent
                    )
                )
                
                logger.info(f"[RABBITMQ] Published message to routing key '{routing_key}' (exchange: {self._exchange_name})")
                logger.debug(f"[RABBITMQ] Message content: {json.dumps(message)[:200]}")
                return True
                
        except pika.exceptions.ChannelClosedByBroker as e:
            logger.error(f"Channel closed by broker while publishing: {e}")
            if "404" in str(e) or "NOT_FOUND" in str(e):
                logger.error(f"Resource not found (404): Exchange '{self._exchange_name}' or queue not found. "
                           f"Message: {e}")
            # Try to reconnect for next time
            self.ensure_publisher_connection()
            return False
        except Exception as e:
            logger.error(f"Error publishing message: {e}", exc_info=True)
            return False
    
    def publish_recommendation(self, recommendation_message: Dict, routing_key: str = 'support.recommendations', batch: bool = False) -> bool:
        """
        Publish recommendation message to RabbitMQ with optional batching.
        
        Args:
            recommendation_message: Message to publish
            routing_key: Routing key for the message
            batch: If True, batch messages for improved throughput
        
        Returns:
            True if published successfully, False otherwise
        """
        if not validate_recommendation_message(recommendation_message):
            logger.error("Invalid recommendation message structure")
            return False
        
        if batch:
            # Add to batch
            with self._batch_lock:
                self._message_batch.append((recommendation_message, routing_key))
                if len(self._message_batch) >= self._batch_size:
                    return self._flush_batch()
            return True
        
        # Immediate publish
        if not self.ensure_publisher_connection():
            logger.error("Cannot publish: publisher connection not available")
            return False
        
        try:
            with self._publisher_lock:
                if not self._publisher_channel or self._publisher_channel.is_closed:
                    logger.warning("Publisher channel not available")
                    return False
                
                self._publisher_channel.basic_publish(
                    exchange=self._exchange_name,
                    routing_key=routing_key,
                    body=json.dumps(recommendation_message),
                    properties=pika.BasicProperties(
                        delivery_mode=1  # Non-persistent
                    )
                )
                
                num_actions = len(recommendation_message.get('recommendedActions', []))
                logger.debug(f"Published {num_actions} recommendation(s) to RabbitMQ")
                return True
                
        except pika.exceptions.ChannelClosedByBroker as e:
            logger.error(f"Channel closed by broker while publishing: {e}")
            if "404" in str(e) or "NOT_FOUND" in str(e):
                logger.error(f"Resource not found (404): Exchange '{self._exchange_name}' or queue not found. "
                           f"Message: {e}")
            # Try to reconnect for next time
            self.ensure_publisher_connection()
            return False
        except Exception as e:
            logger.error(f"Error publishing recommendation: {e}", exc_info=True)
            return False
    
    def _flush_batch(self) -> bool:
        """Flush batched messages to RabbitMQ"""
        if not self._message_batch:
            return True
        
        if not self.ensure_publisher_connection():
            logger.error("Cannot publish batch: publisher connection not available")
            return False
        
        try:
            with self._publisher_lock:
                if not self._publisher_channel or self._publisher_channel.is_closed:
                    logger.warning("Publisher channel not available for batch")
                    return False
                
                batch_to_send = self._message_batch.copy()
                self._message_batch.clear()
            
            success_count = 0
            for message, routing_key in batch_to_send:
                try:
                    self._publisher_channel.basic_publish(
                        exchange=self._exchange_name,
                        routing_key=routing_key,
                        body=json.dumps(message),
                        properties=pika.BasicProperties(
                            delivery_mode=1  # Non-persistent
                        )
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"Error publishing batched message: {e}")
            
            logger.debug(f"Published batch of {success_count}/{len(batch_to_send)} messages")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error flushing batch: {e}", exc_info=True)
            return False
    
    def start_consumer(
        self,
        queue_name: str,
        routing_key: str,
        callback: Callable[[Dict], None],
        stop_event: threading.Event
    ) -> threading.Thread:
        """
        Start a consumer thread for a specific queue.
        
        Args:
            queue_name: Name of the queue to consume from
            routing_key: Routing key to bind queue to exchange
            callback: Function to call with parsed message (Dict)
            stop_event: Event to signal when to stop consuming
        
        Returns:
            Thread object (already started)
        """
        def consumer_thread():
            connection = None
            channel = None
            reconnect_delay = 5.0
            
            while not stop_event.is_set():
                try:
                    connection = self.create_connection()
                    channel = connection.channel()
                    
                    channel.exchange_declare(
                        exchange=self._exchange_name,
                        exchange_type='topic',
                        durable=False
                    )
                    channel.queue_declare(queue=queue_name, durable=False)
                    channel.queue_bind(
                        exchange=self._exchange_name,
                        queue=queue_name,
                        routing_key=routing_key
                    )
                    
                    logger.info(f"Consumer started for queue '{queue_name}' with routing key '{routing_key}'")
                    
                    def message_callback(ch, method, properties, body):
                        try:
                            message = json.loads(body.decode('utf-8'))
                            
                            known_agent_topics = ['simulation.agents.announcements', 'support.llm.requests', 'support.llm.responses']
                            if any(topic in str(method.routing_key) for topic in known_agent_topics):
                                callback(message)
                                ch.basic_ack(delivery_tag=method.delivery_tag)
                                return

                            if not validate_state_update(message):
                                # Only log warning if it doesn't look like an agent announcement
                                if 'agent_id' not in message and 'agentId' not in message:
                                    logger.warning(f"Invalid state update message structure: {list(message.keys())}")
                                ch.basic_ack(delivery_tag=method.delivery_tag)
                                return
                            
                            callback(message)
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode message from {queue_name}: {e}")
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        except Exception as e:
                            logger.error(f"Error processing message from {queue_name}: {e}", exc_info=True)
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    
                    channel.basic_consume(
                        queue=queue_name,
                        on_message_callback=message_callback,
                        auto_ack=False
                    )
                    
                    logger.info(f"Waiting for messages in queue '{queue_name}'...")
                    stop_checker = None
                    stop_requested = threading.Event()
                    
                    def check_stop():
                        while not stop_event.is_set():
                            time.sleep(0.1)
                        stop_requested.set()
                        if channel and channel.is_open:
                            try:
                                channel.stop_consuming()
                                logger.info(f"Stopped consuming from queue: {queue_name}")
                            except Exception as e:
                                logger.debug(f"Error stopping consumer: {e}")
                    
                    stop_checker = threading.Thread(target=check_stop, daemon=False, name=f"StopChecker-{queue_name}")
                    stop_checker.start()
                    
                    try:
                        channel.start_consuming()
                    except Exception as e:
                        if stop_event.is_set() or stop_requested.is_set():
                            logger.info(f"Consumer for queue {queue_name} stopped (stop event set)")
                        else:
                            logger.error(f"Error in start_consuming for queue {queue_name}: {e}", exc_info=True)
                    finally:
                        if stop_checker and stop_checker.is_alive():
                            stop_checker.join(timeout=1.0)
                    
                except pika.exceptions.AMQPConnectionError as e:
                    logger.error(f"RabbitMQ connection error for queue '{queue_name}': {e}")
                    if not stop_event.is_set():
                        time.sleep(reconnect_delay)
                except pika.exceptions.ChannelClosedByBroker as e:
                    logger.error(f"Channel closed by broker for queue '{queue_name}': {e}")
                    if "404" in str(e) or "NOT_FOUND" in str(e):
                        logger.error(f"Resource not found (404): Exchange '{self._exchange_name}' or queue '{queue_name}' "
                                   f"not found. Check RabbitMQ configuration.")
                    if not stop_event.is_set():
                        time.sleep(reconnect_delay)
                except Exception as e:
                    logger.error(f"Unexpected error in consumer for queue '{queue_name}': {e}", exc_info=True)
                    if not stop_event.is_set():
                        time.sleep(reconnect_delay)
                finally:
                    try:
                        if channel and not channel.is_closed:
                            channel.close()
                    except (pika.exceptions.ConnectionClosed, pika.exceptions.ChannelClosed, ConnectionResetError, IndexError):
                        pass
                    except Exception as e:
                        logger.debug(f"Error closing consumer channel: {e}")
                    try:
                        if connection and not connection.is_closed:
                            connection.close()
                    except (pika.exceptions.ConnectionClosed, ConnectionResetError, IndexError):
                        pass
                    except Exception as e:
                        logger.debug(f"Error closing consumer connection: {e}")
            
            logger.info(f"Consumer thread for queue '{queue_name}' stopped")
        
        thread = threading.Thread(target=consumer_thread, daemon=False, name=f"RabbitMQConsumer-{queue_name}")
        thread.start()
        return thread
    
    def purge_queues(self, queue_names: List[str]) -> None:
        """
        Purge (clear) all messages from given RabbitMQ queues.
        Useful when we want to start a completely fresh simulation/support session.
        """
        if not queue_names:
            return

        connection = None
        channel = None
        try:
            connection = self.create_connection()
            channel = connection.channel()

            for queue_name in queue_names:
                try:
                    channel.queue_declare(queue=queue_name, durable=False)
                    result = channel.queue_purge(queue=queue_name)
                    purged = getattr(result.method, "message_count", 0)
                    logger.info(f"Purged queue '{queue_name}' (removed {purged} messages)")
                except Exception as e:
                    # Don't fail whole purge because of one queue
                    logger.debug(f"Failed to purge queue '{queue_name}': {e}")
        except Exception as e:
            logger.error(f"Error purging RabbitMQ queues {queue_names}: {e}", exc_info=True)
        finally:
            try:
                if channel and not channel.is_closed:
                    channel.close()
            except Exception:
                pass
            try:
                if connection and not connection.is_closed:
                    connection.close()
            except Exception:
                pass

    def close(self):
        """Close all connections and clear pending messages"""
        self._stop_event.set()
        
        # Flush and clear any pending message batches
        with self._batch_lock:
            if self._message_batch:
                logger.debug(f"Clearing {len(self._message_batch)} pending messages from batch")
                self._message_batch.clear()
        
        with self._publisher_lock:
            self._close_publisher()
        
        logger.info("RabbitMQ handler closed and cleaned up")
