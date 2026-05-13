import logging
import json
import asyncio
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from src.engine.models.agents.agent import Agent
from src.engine.models.map.sector import Sector
from src.llm.llm_client import LLMClient, LLMPromptManager

logger = logging.getLogger(__name__)

class LLMAgentBrain:
    """
    The 'Brain' of an autonomous agent powered by LLM.
    Handles perception processing, peer coordination, and decision making.
    """
    
    def __init__(
        self, 
        agent_id: str, 
        agent_type: str = "Fire Brigade",
        enable_llm: bool = True,
        llm_config: Optional[Dict] = None
    ):
        self._agent_id = agent_id
        self._agent_type = agent_type
        self._enable_llm = enable_llm
        self._llm_client = LLMClient(**(llm_config or {})) if enable_llm else None
        self._last_decision_time = 0
        self._decision_cooldown = 10.0  
        self._current_plan: Optional[Dict] = None
        self._reasoning: str = "Initialized"

    def analyze_peer_announcements(self, agent: Agent, announcements: List[Dict]) -> Optional[Dict]:
        """
        Analyze what other agents are doing and adjust plan if needed.
        (Heuristic-based coordination before falling back to LLM).
        """
        if not announcements:
            return None
        my_target = agent._destination
        
        return None

    async def make_autonomous_decision(self, 
                                     agent: Agent, 
                                     all_sectors: List[Sector],
                                     peer_announcements: List[Dict],
                                     current_time: float) -> Optional[Dict]:
        """
        Main entry point for autonomous behavior.
        Processes context and returns a command if a new decision is made.
        """
        if not self._enable_llm or not self._llm_client:
            return None

        if current_time - self._last_decision_time < self._decision_cooldown:
            return None

        sectors_with_fires = [s for s in all_sectors if s.fire_level > 0]
        
        if not sectors_with_fires and agent.state.value == "idle":
            return None

        logger.debug(f"[LLM-BRAIN] {self._agent_id} is making an autonomous decision...")
        system_prompt = LLMPromptManager.get_system_prompt(self._agent_id, self._agent_type)
        wind_speed = 5.0 
        wind_dir = "North"
        
        user_context = f"""
Current Status:
- Your Location: ({agent.location.latitude:.4f}, {agent.location.longitude:.4f})
- Your State: {agent.state.value}
- Base Location: ({agent.base_location.latitude:.4f}, {agent.base_location.longitude:.4f})

Environment & Peers:
{LLMPromptManager.format_environment_context(sectors_with_fires, [], wind_speed, wind_dir)}

Recent Peer Actions:
{self._format_peer_actions(peer_announcements)}

Current Plan: {self._reasoning}

What is your next action? Output ONLY valid JSON.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_context}
        ]

        try:
            self._last_decision_time = current_time
            response = await self._llm_client.chat_completion(
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            if response:
                decision = json.loads(response)
                self._reasoning = decision.get("reasoning", "No reasoning provided")
                logger.debug(f"[LLM-BRAIN] {self._agent_id} decided: {decision.get('type')} - {self._reasoning}")
                return decision
                
        except Exception as e:
            logger.error(f"Autonomous decision failed for {self._agent_id}: {e}")
            
        return None

    def _format_peer_actions(self, announcements: List[Dict]) -> str:
        if not announcements:
            return "No recent peer announcements."
            
        lines = []
        now = time.time()
        for ann in announcements:
            age = int(now - ann.get("timestamp", 0))
            if age < 300: # Only show last 5 mins
                lines.append(f"- Agent {ann.get('agent_id')} ({age}s ago): {ann.get('action')} in sector {ann.get('target_sector_id')}")
        
        return "\n".join(lines) if lines else "No recent peer announcements."

    @property
    def reasoning(self) -> str:
        return self._reasoning
