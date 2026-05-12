import json
import logging
from typing import Optional, List, Dict, Any

from simulation.forest_map import ForestMap
from simulation.agent_state import AGENT_STATE
from simulation.agent import Agent
from simulation.fire_brigades.fire_brigade import FireBrigade
from simulation.forester_patrols.forester_patrol import ForesterPatrol
from simulation.agent_manager.action_type import *
from simulation.sectors.sector import Sector

logger = logging.getLogger(__name__)

class AgentManager:
    def __init__(
        self,
        map : ForestMap,
        storage,  # MessageStore or similar storage interface
        engine=None,
        llm_client=None,
        agent_communication=None
    ):
        self._engine = engine
        self._map = map
        self._storage = storage
        
        # LLM and communication capabilities (optional)
        self._llm_client = llm_client
        self._agent_communication = agent_communication

        self._brigades = {
            fire_brigade.fire_brigade_id: fire_brigade
            for fire_brigade in map._fire_brigades
        }

        self._patrols = {
            patrol.forester_patrol_id: patrol
            for patrol in map._forester_patrols
        }

        self._agents = {
            agent: map.find_sector(agent.location)
            for agent in map._fire_brigades + map._forester_patrols
        }
        
        # Inject LLM capabilities into agents if available
        if self._llm_client or self._agent_communication:
            self._inject_llm_capabilities()

    @property
    def brigades(self):
        return self._brigades
    
    @property
    def patrols(self):
        return self._patrols
    
    @property
    def agents(self):
        return self._agents
    
    def update_state(self, agent: Agent):
        if agent.state == AGENT_STATE.TRAVELLING:
            if self.update_position(agent):
                agent._location = agent.destination
                if agent.destination == agent.base_location:
                    agent.set_state_available()
                else:
                    agent.set_state_executing()
                    agent.increment_agents_in_sector(self.agents[agent]) 

        elif agent.state == AGENT_STATE.EXECUTING:
            if agent.is_task_finished(self.agents[agent]):
                agent.set_state_available()

    def _calculate_step(self, target: float, current: float, delta: float) -> float:
        return min(delta, target - current) if target > current else max(-delta, target - current) if target < current else 0

    def update_position(self, agent : Agent) -> bool:
        speed_factor = getattr(self._engine, 'speed_factor', 1.0)
        base_delta = 0.005
        delta = base_delta * speed_factor
        agent.location.latitude += self._calculate_step(agent.destination.latitude, agent.location.latitude, delta)
        agent.location.longitude += self._calculate_step(agent.destination.longitude, agent.location.longitude, delta)

        self.agents[agent] = self._map.find_sector(agent.location)
        self._storage.add_message_to_sent(self._get_queue_name(agent), generate_traveling_message(agent))

        at_destination = (
            abs(agent.destination.latitude - agent.location.latitude) <= 0.001 and
            abs(agent.destination.longitude - agent.location.longitude) <= 0.001
        )
        return at_destination

    def update_agents_states(self):
        for agent in self.agents.keys():
            self.update_state(agent)
    
    def _inject_llm_capabilities(self):
        """Inject LLM client and agent communication into fire brigades."""
        if not self._llm_client and not self._agent_communication:
            logger.debug("[AgentManager] No LLM capabilities to inject")
            return
        
        injected_count = 0
        for brigade in self._brigades.values():
            if isinstance(brigade, FireBrigade):
                # Set LLM capabilities if not already set
                llm_injected = False
                comm_injected = False
                
                if self._llm_client:
                    if hasattr(brigade, '_llm_client') and brigade._llm_client is None:
                        brigade._llm_client = self._llm_client
                        llm_injected = True
                    elif not hasattr(brigade, '_llm_client'):
                        brigade._llm_client = self._llm_client
                        llm_injected = True
                
                if self._agent_communication:
                    if hasattr(brigade, '_agent_communication') and brigade._agent_communication is None:
                        brigade._agent_communication = self._agent_communication
                        comm_injected = True
                    elif not hasattr(brigade, '_agent_communication'):
                        brigade._agent_communication = self._agent_communication
                        comm_injected = True
                
                if llm_injected or comm_injected:
                    logger.debug(f"[LLM-AGENT] FireBrigade {brigade.fire_brigade_id} - "
                               f"LLM: {' ' if llm_injected else ' '}, "
                               f"Communication: {' ' if comm_injected else ' '}")
                    injected_count += 1
        
        if injected_count > 0:
            logger.info("=" * 80)
            logger.debug(f"[LLM-AGENT] Successfully initialized LLM capabilities for {injected_count} fire brigades")
            logger.info("=" * 80)
        else:
            logger.debug("[LLM-AGENT] No fire brigades needed LLM injection")
    
    def enable_llm_for_agents(self, llm_client, agent_communication):
        """
        Enable LLM capabilities for all agents.
        
        Args:
            llm_client: LLMClient instance
            agent_communication: AgentCommunication instance
        """
        self._llm_client = llm_client
        self._agent_communication = agent_communication
        self._inject_llm_capabilities()
        logger.info("Enabled LLM capabilities for all agents")
    
    def make_autonomous_decision(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Make an autonomous LLM-based decision for an agent.
        
        Args:
            agent_id: ID of the agent
            
        Returns:
            Decision dict or None if LLM not available or agent not found
        """
        if not self._llm_client:
            return None
        
        brigade = self._brigades.get(agent_id)
        if not isinstance(brigade, FireBrigade):
            return None
        
        try:
            all_sectors = self._get_all_sectors()
            available_sectors = [s for s in all_sectors if hasattr(s, 'fire_level') and s.fire_level > 0]
            
            # Get peer announcements
            peer_announcements = []
            if self._agent_communication:
                peer_announcements = brigade.get_peer_announcements(max_count=50)
            
            # Make decision
            decision = brigade.make_llm_decision(available_sectors, peer_announcements)
            
            # Announce action if decision was made
            if decision and self._agent_communication:
                action_type = "moving_to" if decision.get("decision") == "move_to" else "stay_idle"
                brigade.announce_action(
                    action=action_type,
                    target_sector_id=decision.get("target_sector_id"),
                    reasoning=decision.get("reasoning")
                )
            
            return decision
            
        except Exception as e:
            logger.error(f"Error making autonomous decision for agent {agent_id}: {e}", exc_info=True)
            return None
    
    def _get_all_sectors(self) -> List[Sector]:
        """Get all sectors from the map."""
        sectors = []
        for row in self._map._sectors:
            for sector in row:
                if sector:
                    sectors.append(sector)
        return sectors

    