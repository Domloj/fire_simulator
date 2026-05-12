"""
MessageStore adapter for fire-support's RabbitMQHandler.
This adapter allows AgentCommunication to work with RabbitMQHandler instead of MessageStore.
"""
import logging
import json
import threading
from collections import defaultdict, deque
from typing import Optional

logger = logging.getLogger(__name__)


class MessageStoreAdapter:
    """
    Adapter that provides MessageStore-like interface for RabbitMQHandler.
    Allows AgentCommunication to work with RabbitMQHandler.
    """
    
    def __init__(self, rabbitmq_handler):
        self._rabbitmq = rabbitmq_handler
        self._messages_to_sent = defaultdict(deque)
        self._received_messages = defaultdict(deque)
        self._lock = threading.Lock()
        self._consumed_queues = set()
        self._queue_callbacks = {}
        self._stop_events = {}
        
        logger.info("[MSG-STORE-ADAPTER] Initialized")
    
    def add_received_message(self, message, queue_name: str) -> None:
        """Add a received message to the store."""
        with self._lock:
            self._received_messages[queue_name].append(message)
    
    def add_message_to_sent(self, queue_name: str, message) -> None:
        """
        Add a message to be sent.
        Publishes immediately via RabbitMQ.
        """
        routing_key = self._queue_to_routing_key(queue_name)
        logger.info(f"[MSG-STORE-ADAPTER] Publishing message - Queue: {queue_name}, Routing Key: {routing_key}")
        
        if isinstance(message, dict):
            message_body = json.dumps(message)
        else:
            message_body = message if isinstance(message, str) else json.dumps(message)
        
        try:
            message_dict = message if isinstance(message, dict) else json.loads(message_body)
            success = self._rabbitmq.publish_message(message_dict, routing_key=routing_key, validate=False)
            
            if success:
                with self._lock:
                    self._messages_to_sent[queue_name].append(message)
        except Exception as e:
            logger.error(f"[MSG-STORE-ADAPTER]   Exception while publishing message: {e}", exc_info=True)
    
    def get_message_to_sent(self, queue_name: str):
        """Get and remove oldest message from sent queue."""
        with self._lock:
            if self._messages_to_sent[queue_name]:
                return self._messages_to_sent[queue_name].popleft()
            return None
    
    def get_received_message(self, queue_name):
        """Get and remove oldest received message."""
        with self._lock:
            if self._received_messages[queue_name]:
                return self._received_messages[queue_name].popleft()
            return None
    
    def setup_consumer(self, queue_name: str, routing_key: str, stop_event, callback=None):
        """
        Set up a consumer for a queue.
        Messages will be automatically added to received_messages.
        If callback is provided, it will be called in addition to storing the message.
        """
        if queue_name in self._consumed_queues:
            return None
        
        def message_callback(message: dict):
            """Callback to handle received messages."""
            self.add_received_message(message, queue_name)
            if callback:
                try:
                    callback(message)
                except Exception as e:
                    logger.error(f"[MSG-STORE-ADAPTER] Error in callback for {queue_name}: {e}", exc_info=True)
        
        thread = self._rabbitmq.start_consumer(
            queue_name=queue_name,
            routing_key=routing_key,
            callback=message_callback,
            stop_event=stop_event
        )
        
        self._consumed_queues.add(queue_name)
        self._queue_callbacks[queue_name] = message_callback
        self._stop_events[queue_name] = stop_event
        
        logger.info(f"[MSG-STORE-ADAPTER] Set up consumer for queue: {queue_name} (routing: {routing_key})")
        return thread
    
    def clear(self):
        """Clear all messages."""
        with self._lock:
            self._messages_to_sent.clear()
            self._received_messages.clear()
        logger.debug("[MSG-STORE-ADAPTER] Cleared all messages")
    
    def _queue_to_routing_key(self, queue_name: str) -> str:
        """Convert queue name to routing key."""
        mapping = {
            "simulation_agents_announcements": "simulation.agents.announcements",
            "agent_announcements": "simulation.agents.announcements",
            "agent_communication": "simulation.agents.communication",
        }
        
        if "." in queue_name:
            return queue_name
        
        routing_key = mapping.get(queue_name)
        if routing_key:
            logger.debug(f"[MSG-STORE-ADAPTER] Mapped queue '{queue_name}' -> routing key '{routing_key}'")
            return routing_key
        
        routing_key = queue_name.replace("_", ".")
        logger.debug(f"[MSG-STORE-ADAPTER] Converted queue '{queue_name}' -> routing key '{routing_key}'")
        return routing_key
