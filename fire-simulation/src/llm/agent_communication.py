import logging
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.rabbitmq.message_store import MessageStore
from src.messaging.topics import TopicRegistry

logger = logging.getLogger(__name__)

class AgentCommunication:
    """
    Handles peer-to-peer communication between agents for coordination.
    Uses RabbitMQ to broadcast agent intentions and status updates.
    """
    
    def __init__(self, message_store: MessageStore):
        self._message_store = message_store
        self._announcement_topic = TopicRegistry.AGENT_ANNOUNCEMENTS.value
        self._communication_topic = TopicRegistry.AGENT_COMMUNICATION.value
        self._llm_request_topic = "support.llm.requests"  # Matching TopicRegistry in fire-support
        self._llm_responses_topic = "support.llm.responses"  # Coordinator responses
        self._llm_propositions_responses_topic = "support.llm.propositions.responses"  # Proposition responses
        self._recent_announcements: List[Dict] = []
        self._recent_coordinator_responses: List[Dict] = []
        self._max_stored_announcements = 50
        self._last_chat_message_time: Dict[str, float] = {}  # Track last message time per agent
        self._chat_message_timeout = 2.0  # 2 seconds timeout between messages

    def announce_to_llm_chat(self, order_message: Dict):
        """Publish BrigadeOrder to strategic LLM chat queue with 2 second timeout"""
        try:
            agent_id = order_message.get("agentId", "unknown")
            current_time = time.time()
            
            # Check if enough time has passed since last message from this agent
            last_time = self._last_chat_message_time.get(agent_id, 0)
            time_since_last = current_time - last_time
            
            if time_since_last < self._chat_message_timeout:
                # Skip sending - too soon
                return
            
            # Update last message time
            self._last_chat_message_time[agent_id] = current_time
            
            # Explicitly use the routing key string to ensure it matches fire-support
            routing_key = "support.llm.requests"
            self._message_store.add_message_to_sent(routing_key, order_message)
        except Exception as e:
            logger.error(f"Failed to send LLM chat announcement: {e}")

    def announce_action(
        self, 
        agent_id: str, 
        action: str, 
        target_sector_id: Optional[int] = None,
        location: Optional[Dict[str, float]] = None,
        reasoning: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None
    ):
        """Broadcast current agent intention to all other agents"""
        message = {
            "agent_id": agent_id,
            "timestamp": time.time(),
            "iso_time": datetime.now().isoformat(),
            "action": action,
            "target_sector_id": target_sector_id,
            "location": location,
            "reasoning": reasoning
        }
        
        if additional_data:
            message.update(additional_data)
        
        try:
            self._message_store.add_message_to_sent(self._announcement_topic, message)
        except Exception as e:
            logger.error(f"Failed to send agent announcement: {e}")

    def send_direct_message(self, from_agent: str, to_agent: str, msg_type: str, content: Dict):
        """Send a direct message to a specific agent (simulated via topic routing)"""
        message = {
            "from_agent": from_agent,
            "to_agent": to_agent,
            "type": msg_type,
            "timestamp": time.time(),
            "content": content
        }
        
        try:
            # We use a combined communication topic but include to_agent filter in the message
            self._message_store.add_message_to_sent(self._communication_topic, message)
        except Exception as e:
            logger.error(f"Failed to send direct message: {e}")

    def send_proposition_to_coordinator(self, agent_id: str, proposition: str):
        """Send a strategic proposition to the coordinator for evaluation"""
        message = {
            "agentId": agent_id,
            "type": "AgentProposition",
            "description": proposition,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Send on the propositions queue for coordinator to handle
            routing_key = "support.llm.propositions"
            self._message_store.add_message_to_sent(routing_key, message)
        except Exception as e:
            logger.error(f"Failed to send proposition: {e}", exc_info=True)

    def get_recent_announcements(self, max_count: int = 10) -> List[Dict]:
        """Get latest messages from the strategic chat (peers and coordinator)"""
        # We need to check both requests (agent talks) and responses (coordinator talks)
        queues = ["support_llm_requests", "support_llm_responses", "simulation_agents_announcements"]
        
        try:
            for q in queues:
                while True:
                    msg = self._message_store.get_received_message(q)
                    if not msg: break
                    # Normalize description field if it is a natural language message
                    if "description" in msg and "description" not in msg:
                        pass # Already normalized
                    self._recent_announcements.append(msg)
            
            # Keep only most recent
            if len(self._recent_announcements) > self._max_stored_announcements:
                self._recent_announcements = self._recent_announcements[-self._max_stored_announcements:]
            
            return self._recent_announcements[-max_count:]
        except Exception as e:
            logger.error(f"Error fetching recent chat: {e}")
            return []

    def get_coordinator_responses(self, max_count: int = 10) -> List[Dict]:
        """Get responses from the Strategic Coordinator on agent propositions"""
        queues = ["support_llm_responses", "support_llm_propositions_responses"]
        
        try:
            for q in queues:
                while True:
                    msg = self._message_store.get_received_message(q)
                    if not msg: 
                        break
                    self._recent_coordinator_responses.append(msg)
            
            # Keep only most recent
            if len(self._recent_coordinator_responses) > self._max_stored_announcements:
                self._recent_coordinator_responses = self._recent_coordinator_responses[-self._max_stored_announcements:]
            
            return self._recent_coordinator_responses[-max_count:]
        except Exception as e:
            logger.error(f"Error fetching coordinator responses: {e}")
            return []

    def get_messages_for_agent(self, agent_id: str) -> List[Dict]:
        """Get direct messages intended for this agent"""
        queue_name = self._communication_topic.replace('.', '_')
        messages = []
        
        try:
            # Fetch and filter
            raw_msgs = []
            while True:
                msg = self._message_store.get_received_message(queue_name)
                if not msg:
                    break
                raw_msgs.append(msg)
            
            for msg in raw_msgs:
                if msg.get("to_agent") == agent_id:
                    messages.append(msg)
            
            return messages
        except Exception as e:
            logger.error(f"Error fetching messages for agent {agent_id}: {e}")
            return []
class CoordinationLogic:
    """Helper for agents to resolve conflicts based on peer data"""
    
    @staticmethod
    def is_sector_occupied(sector_id: int, announcements: List[Dict], exclude_agent: str) -> bool:
        """Check if any OTHER agent has already claimed this sector"""
        now = time.time()
        for ann in announcements:
            # Only consider recent announcements (within last 2 minutes)
            if ann.get("agent_id") != exclude_agent and ann.get("target_sector_id") == sector_id:
                if now - ann.get("timestamp", 0) < 120:
                    return True
        return False

    @staticmethod
    def get_agents_per_sector(announcements: List[Dict]) -> Dict[int, List[str]]:
        """Count how many agents are assigned to each sector"""
        counts = {}
        now = time.time()
        for ann in announcements:
            if now - ann.get("timestamp", 0) < 120:
                sid = ann.get("target_sector_id")
                if sid is not None:
                    if sid not in counts:
                        counts[sid] = []
                    counts[sid].append(ann.get("agent_id"))
        return counts

