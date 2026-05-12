import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import deque

from llm.message_store_adapter import MessageStoreAdapter
from llm.topics import TopicRegistry

logger = logging.getLogger(__name__)

class AgentCommunication:
    """
    Handles inter-agent communication via RabbitMQ.
    Fire brigades can announce their actions so others can coordinate.
    """
    
    def __init__(self, message_store: MessageStoreAdapter, announcement_retention_seconds: float = 30.0):
        """
        Initialize agent communication system.
        
        Args:
            message_store: MessageStoreAdapter for RabbitMQ communication
            announcement_retention_seconds: How long to keep announcements in memory
        """
        self._message_store = message_store
        self._announcement_retention = timedelta(seconds=announcement_retention_seconds)
        self._recent_announcements: deque = deque()  # Store recent announcements
        self._announcement_topic = TopicRegistry.AGENT_ANNOUNCEMENTS.value
        
        logger.info("=" * 80)
        logger.info("[AGENT-COMM] INITIALIZATION")
        logger.info("=" * 80)
        logger.info(f"MessageStore: {'Available' if message_store else 'Not available'}")
        logger.info(f"Announcement Topic: {self._announcement_topic}")
        logger.info(f"Retention Period: {announcement_retention_seconds}s")
        logger.info(f"Queue Name: {self._announcement_topic.replace('.', '_')}")
        logger.info("=" * 80)
    
    def announce_action(
        self,
        agent_id: str,
        action: str,
        target_sector_id: Optional[int] = None,
        location: Optional[Dict[str, float]] = None,
        reasoning: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """
        Announce an action to other agents.
        
        Args:
            agent_id: ID of the agent making the announcement
            action: Type of action ("order_received", "moving_to", "starting_extinguish", "task_complete")
            target_sector_id: Sector ID if applicable
            location: Location if applicable
            reasoning: Reason for the action (optional)
            additional_data: Any additional data
        """
        announcement = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": agent_id,
            "action": action,
            "target_sector_id": target_sector_id,
            "location": location,
            "reasoning": reasoning,
            **(additional_data or {})
        }
        
        self._recent_announcements.append(announcement)
        
        if self._message_store:
            queue_name = self._announcement_topic.replace('.', '_')
            try:
                logger.info(f"[AGENT-COMM] Publishing announcement from {agent_id}: {action} "
                           f"(sector: {target_sector_id}, queue: {queue_name}, routing: {self._announcement_topic})")
                self._message_store.add_message_to_sent(queue_name, announcement)
                logger.info(f"[AGENT-COMM] Announcement from {agent_id} sent successfully")
            except Exception as e:
                logger.error(f"[AGENT-COMM] Failed to send announcement from {agent_id}: {e}", exc_info=True)
        else:
            logger.warning(f"[AGENT-COMM] MessageStore not available - announcement from {agent_id} not sent")
    
    def get_recent_announcements(
        self,
        exclude_agent_id: Optional[str] = None,
        action_filter: Optional[str] = None,
        max_count: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get recent announcements from other agents.
        
        Args:
            exclude_agent_id: Agent ID to exclude (typically self)
            action_filter: Filter by action type (optional)
            max_count: Maximum number of announcements to return
            
        Returns:
            List of recent announcements
        """
        self._clean_old_announcements()
        self._consume_rabbitmq_announcements()
        
        announcements = []
        cutoff_time = datetime.now() - self._announcement_retention
        
        for ann in self._recent_announcements:
            try:
                timestamp = ann.get("timestamp")
                if timestamp is None:
                    continue
                
                # Handle different timestamp formats
                if isinstance(timestamp, str):
                    ann_time = datetime.fromisoformat(timestamp)
                elif isinstance(timestamp, (int, float)):
                    # Unix timestamp (seconds since epoch)
                    ann_time = datetime.fromtimestamp(timestamp)
                elif isinstance(timestamp, datetime):
                    ann_time = timestamp
                else:
                    continue

                if (
                    ann_time < cutoff_time or
                    (exclude_agent_id and ann.get("agent_id") == exclude_agent_id) or
                    (action_filter and ann.get("action") != action_filter)
                ):
                    continue
                
                announcements.append(ann)
                
                if len(announcements) >= max_count:
                    break
                    
            except (KeyError, ValueError) as e:
                logger.warning(f"[AGENT-COMM] Invalid announcement format: {e}")
                continue
        
        return announcements
    
    def get_peer_actions_for_sector(
        self,
        sector_id: int,
        exclude_agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """ Get actions from peers related to a specific sector. """
        announcements = self.get_recent_announcements(exclude_agent_id=exclude_agent_id)
        return [
            ann for ann in announcements
            if ann.get("target_sector_id") == sector_id
        ]
    
    def _clean_old_announcements(self):
        """Remove announcements older than retention period"""
        if not self._recent_announcements:
            return
        
        cutoff_time = datetime.now() - self._announcement_retention
        
        while self._recent_announcements:
            try:
                timestamp = self._recent_announcements[0].get("timestamp")
                if timestamp is None:
                    self._recent_announcements.popleft()
                    continue
                
                # Handle different timestamp formats
                if isinstance(timestamp, str):
                    first_time = datetime.fromisoformat(timestamp)
                elif isinstance(timestamp, (int, float)):
                    # Unix timestamp (seconds since epoch)
                    first_time = datetime.fromtimestamp(timestamp)
                elif isinstance(timestamp, datetime):
                    first_time = timestamp
                else:
                    # Unknown format, remove it
                    logger.debug(f"[AGENT-COMM] Unknown timestamp format: {type(timestamp)}, removing announcement")
                    self._recent_announcements.popleft()
                    continue
                
                if first_time >= cutoff_time:
                    break
                self._recent_announcements.popleft()
            except (KeyError, ValueError, TypeError, OSError) as e:
                logger.debug(f"[AGENT-COMM] Error parsing timestamp, removing announcement: {e}")
                self._recent_announcements.popleft()
    
    def _consume_rabbitmq_announcements(self):
        """Consume new announcements from RabbitMQ queue"""
        if not self._message_store:
            return
        
        queue_name = self._announcement_topic.replace('.', '_')
        
        for _ in range(10):
            message = self._message_store.get_received_message(queue_name)
            if not message:
                break
            
            try:
                if isinstance(message, dict) and "agent_id" in message and "action" in message:
                    is_duplicate = any(
                        (a.get("agent_id") == message.get("agent_id") and
                         a.get("action") == message.get("action") and
                         a.get("timestamp") == message.get("timestamp"))
                        for a in self._recent_announcements
                    )
                    
                    if not is_duplicate:
                        self._recent_announcements.append(message)
            except Exception as e:
                logger.warning(f"[AGENT-COMM] Failed to process announcement from RabbitMQ: {e}")
    
    def setup_consumer(self, stop_event, callback=None):
        """Set up consumer for agent announcements."""
        if self._message_store:
            queue_name = self._announcement_topic.replace('.', '_')
            
            def wrapped_callback(message: dict):
                if callback:
                    callback(message)
                try:
                    if isinstance(message, dict) and "agent_id" in message and "action" in message:
                        is_duplicate = any(
                            (a.get("agent_id") == message.get("agent_id") and
                             a.get("action") == message.get("action") and
                             a.get("timestamp") == message.get("timestamp"))
                            for a in self._recent_announcements
                        )
                        if not is_duplicate:
                            self._recent_announcements.append(message)
                except Exception as e:
                    logger.warning(f"[AGENT-COMM] Failed to store announcement: {e}")
            
            return self._message_store.setup_consumer(
                queue_name=queue_name,
                routing_key=self._announcement_topic,
                stop_event=stop_event,
                callback=wrapped_callback if callback else None
            )
        return None
    
    def clear(self):
        """Clear all stored announcements"""
        self._recent_announcements.clear()
        logger.debug("[AGENT-COMM] Cleared all announcements")
