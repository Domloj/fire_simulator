import logging
from collections import deque
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class MessageStore:
    def __init__(self, max_size: int = 1000):
        self._received_messages: Dict[str, deque] = {}
        self._sent_messages: Dict[str, deque] = {}
        self._max_size = max_size

    def add_received_message(self, message: Dict[str, Any], queue_name: str):
        if queue_name not in self._received_messages:
            self._received_messages[queue_name] = deque(maxlen=self._max_size)
        self._received_messages[queue_name].append(message)

    def get_received_message(self, queue_name: str) -> Optional[Dict[str, Any]]:
        if queue_name in self._received_messages and self._received_messages[queue_name]:
            return self._received_messages[queue_name].popleft()
        return None

    def add_message_to_sent(self, topic: str, message: Dict[str, Any]):
        if topic not in self._sent_messages:
            self._sent_messages[topic] = deque(maxlen=self._max_size)
        self._sent_messages[topic].append(message)

    def get_all_sent_messages(self, topic: str) -> List[Dict[str, Any]]:
        if topic in self._sent_messages:
            return list(self._sent_messages[topic])
        return []

    def clear_sent_messages(self, topic: str):
        if topic in self._sent_messages:
            self._sent_messages[topic].clear()

    def clear(self):
        self._received_messages.clear()
        self._sent_messages.clear()
