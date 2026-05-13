import pika
import logging
from contextlib import contextmanager
from typing import Iterator, Tuple, Optional
from src.settings.communucation_settings import get_communication_settings
from src.rabbitmq.connection_manager import RabbitMQConnectionManager

logger = logging.getLogger(__name__)

class PikaClient:
    def __init__(self):
        self._settings = get_communication_settings()
        self._connection_manager = RabbitMQConnectionManager(self._settings)

    def create_connection(self) -> pika.BlockingConnection:
        return self._connection_manager.get_connection()

    @contextmanager
    def connection_ctx(self) -> Iterator[Tuple[Optional[pika.BlockingConnection], Optional[pika.channel.Channel]]]:
        try:
            conn = self._connection_manager.get_connection()
            ch = conn.channel()
            yield conn, ch
        except Exception as e:
            logger.exception("Pika connection error: %s", e)
            yield None, None
