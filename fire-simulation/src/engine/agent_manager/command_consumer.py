import logging
import threading
import time
from typing import Callable, Optional

from src.rabbitmq.message_store import MessageStore
from src.messaging.topics import TopicRegistry
from src.engine.agent_manager.agent_type_config import get_all_agent_configs, AgentTypeConfig
from src.engine.models.map.forest_map import ForestMap
from src.engine.models.core.location import Location

logger = logging.getLogger(__name__)

class CommandConsumer:
    """
    Consumes commands from RabbitMQ and forwards to AgentManager.
    Runs in background thread to continuously process incoming commands.
    """
    
    def __init__(self, message_store: MessageStore, command_callback: Callable, forest_map: Optional[ForestMap] = None):
        self._message_store = message_store
        self._command_callback = command_callback
        self._forest_map = forest_map
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_command_hash = {}

        if forest_map:
            logger.info("[CONSUMER] CommandConsumer initialized with forest_map for sector lookup")
        else:
            logger.warning("[CONSUMER] CommandConsumer initialized without forest_map - sector lookup disabled")
    
    def start(self):
        """Start consuming commands in background thread"""
        if self._thread and self._thread.is_alive():
            logger.warning("CommandConsumer already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._consume_loop, daemon=True, name="CommandConsumer")
        self._thread.start()
        logger.info("CommandConsumer started")
    
    def stop(self):
        """Stop consuming commands and clear state"""
        logger.info("Stopping CommandConsumer...")
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("CommandConsumer thread did not stop within timeout")
            else:
                logger.info("CommandConsumer thread stopped")
        else:
            logger.info("CommandConsumer thread was not running")

        # Clear command history to prevent duplicate detection issues on restart
        self._last_command_hash.clear()
        self._thread = None
        
        logger.info("CommandConsumer stopped and cleaned up")
    
    def _consume_loop(self):
        """Main consumption loop - simple, polling-based"""
        logger.info("CommandConsumer loop started")
        agent_configs = get_all_agent_configs()

        while not self._stop_event.is_set():
            try:
                for config in agent_configs:
                    queue_name = config.command_topic.replace('.', '_')
                    message = self._message_store.get_received_message(queue_name)
                    if message:
                        self._process_agent_command(message, config)

            except Exception as e:
                logger.error(f"Error in command consumer loop: {e}", exc_info=True)

            time.sleep(1.0)

        logger.info("CommandConsumer loop exited")
    
    def _process_agent_command(self, message: dict, config: AgentTypeConfig):
        """Simplified command processing with small helpers and tuple-based dedupe"""
        try:
            agent_id = self._normalize_agent_id(message, config)
            if not agent_id:
                logger.warning(f"[CONSUMER] {config.display_name} command missing {config.id_field_name}: {message}")
                return

            action = message.get("action")
            going_to_base = (action == "GO_TO_BASE") or message.get("goingToBase", False)
            sector_id, location = self._resolve_sector_and_location(message)

            # Determine task type
            task_type = self._determine_task_type(config.type_name, action, sector_id, going_to_base)

            # Build command
            if going_to_base:
                command = {
                    "type": "return_to_base",
                    "agentId": agent_id,
                    "description": message.get("description", "") or "Return to base",
                    "priority": message.get("priority", 10),
                    "source": "command_consumer"
                }
                key = ("return_to_base", None, None, None)
            else:
                if not location:
                    logger.warning(f"[CONSUMER] {config.display_name} command missing location: {message}")
                    return

                lat = float(location.get("latitude"))
                lon = float(location.get("longitude"))
                description = message.get("description", "") or message.get("reason", "")
                if not description:
                    if task_type == "extinguish":
                        description = f"Extinguish sector {sector_id}" if sector_id else "Extinguish fire"
                    elif task_type == "patrol":
                        description = f"Patrol sector {sector_id}" if sector_id else "Patrol area"

                command = {
                    "type": task_type,
                    "agentId": agent_id,
                    "sectorId": sector_id,
                    "location": {"latitude": lat, "longitude": lon},
                    "description": description,
                    "priority": message.get("priority", 10),
                    "source": "command_consumer"
                }
                key = (task_type, sector_id, round(lat, 6), round(lon, 6))

            if self._is_duplicate(agent_id, key):
                logger.info(f"[CONSUMER] Skipping duplicate command for {agent_id}: {task_type}, sector: {sector_id}")
                return

            self._last_command_hash[agent_id] = key
            logger.info(f"[CONSUMER] Processing new command for {agent_id}: {task_type}, sector: {sector_id}, source: {message.get('source')}")
            self._command_callback(command)

        except Exception as e:
            logger.error(f"Failed to process {config.display_name} command: {e}", exc_info=True)

    def _normalize_agent_id(self, message: dict, config: AgentTypeConfig) -> Optional[str]:
        agent_id = message.get(config.id_field_name)
        if agent_id is None:
            return None
        agent_id = str(agent_id)
        if config.id_field_name == "fireBrigadeId":
            return f"FB-{agent_id}"
        if config.id_field_name == "foresterPatrolId":
            return f"FP-{agent_id}"
        return agent_id

    def _resolve_sector_and_location(self, message: dict):
        sector_id = message.get("sectorId") or message.get("targetSectorId") or message.get("sector_id")
        location = message.get("location")
        if not sector_id and location and self._forest_map:
            try:
                location_obj = Location(
                    latitude=float(location.get("latitude")),
                    longitude=float(location.get("longitude"))
                )
                sector = self._forest_map.find_sector(location_obj)
                if sector:
                    sector_id = sector.sector_id
                    logger.debug(f"[CONSUMER] Looked up sector {sector_id} for location ({location_obj.latitude:.6f}, {location_obj.longitude:.6f})")
                else:
                    logger.debug(f"[CONSUMER] Could not find sector for location ({location_obj.latitude:.6f}, {location_obj.longitude:.6f})")
            except Exception as e:
                logger.warning(f"[CONSUMER] Failed to look up sector from location: {e}")
        return sector_id, location

    def _determine_task_type(self, type_name: str, action: Optional[str], sector_id: Optional[int], going_to_base: bool) -> str:
        if going_to_base:
            return "return_to_base"
        if type_name == "fireBrigade":
            if action == "EXTINGUISH" or (action is None and sector_id is not None):
                return "extinguish"
            return "move_to"
        if type_name == "foresterPatrol":
            if action == "PATROL" or (action is None and sector_id is not None):
                return "patrol"
            return "move_to"
        return "move_to"

    def _is_duplicate(self, agent_id: str, key: tuple) -> bool:
        return self._last_command_hash.get(agent_id) == key
