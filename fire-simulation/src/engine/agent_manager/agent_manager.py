import logging
import os
import time
from typing import Dict, List, Optional
from datetime import datetime
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from src.engine.models.agents.agent import Agent
from src.engine.models.agents.fire_brigade import FireBrigade
from src.engine.models.agents.forester_patrol import ForesterPatrol
from src.engine.models.map.forest_map import ForestMap
from src.engine.models.map.sector import Sector
from src.rabbitmq.message_store import MessageStore
from src.messaging.topics import TopicRegistry
from src.engine.agent_manager.agent_type_config import get_agent_config

logger = logging.getLogger(__name__)

_telemetry_count = 0
_last_telemetry_log = None

class AgentManager:
    """
    Agent orchestration layer - manages agent lifecycle, commands, telemetry.
    Does NOT make decisions - only executes external commands.
    """
    def __init__(
        self, 
        forest_map: ForestMap, 
        message_store: MessageStore = None, 
        engine                      = None
    ):
        self._map = forest_map
        self._message_store = message_store
        self._engine = engine
        self._agents: Dict[str, Agent] = {}
        self._agent_sectors: Dict[str, Optional[Sector]] = {}
        self._brigades: Dict[str, FireBrigade] = {}
        self._patrols: Dict[str, ForesterPatrol] = {}
        self._llm_brains: Dict[str, any] = {} 
        self._agent_communication = None
        self._enable_llm_agents = os.environ.get("ENABLE_LLM_AGENTS", "true").lower() == "true"
        # Thread pool for non-blocking LLM calls in announcements
        self._announcement_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="agent-announce")
        self._announcement_timeout = 1.0  # Max 1s for LLM call, then use template (allows time for network but not too long)
        self._telemetry_batch: Dict[str, List[dict]] = {}
        self._last_telemetry_flush_ts: float = 0.0
        # Metrics for debugging agent update frequency
        self._pos_update_count: int = 0
        self._pos_update_window_start: float = 0.0
        self._agent_last_telemetry_ts: Dict[str, float] = {}
        self._telemetry_throttle_interval: float = 1.0  # seconds between telemetry publishes per agent
        
        for brigade in forest_map.fire_brigades:
            agent_id = f"FB-{brigade.fire_brigade_id}"
            self._agents[agent_id] = brigade
            # numeric_id = str(brigade.fire_brigade_id)
            self._brigades[ str(brigade.fire_brigade_id)] = brigade
            self._agent_sectors[agent_id] = forest_map.find_sector(brigade.location)
            
        
        for patrol in forest_map.forester_patrols:
            agent_id = f"FP-{patrol.forester_patrol_id}"
            self._agents[agent_id] = patrol
            numeric_id = str(patrol.forester_patrol_id)
            self._patrols[numeric_id] = patrol
            self._agent_sectors[agent_id] = forest_map.find_sector(patrol.location)
        
        if self._enable_llm_agents and self._message_store:
            try:
                logger.info("[LLM] Initializing agent communication system...")
                from src.llm.agent_communication import AgentCommunication
                self._agent_communication = AgentCommunication(self._message_store)
                logger.info("[LLM] Agent communication system initialized successfully")
                
                for agent in self._agents.values():
                    agent.set_communication(self._agent_communication)
                logger.info(f"[LLM] Assigned communication adapter to {len(self._agents)} agents")

            except Exception as e:
                logger.error(f"[LLM] Failed to initialize agent communication: {e}", exc_info=True)
                self._agent_communication = None  # Ensure it's None on failure
        
        if self._agent_communication:
            for agent in self._agents.values():
                if hasattr(agent, '_llm_chat_enabled'):
                    agent._llm_chat_enabled = True
                    agent.set_communication(self._agent_communication)
        
        logger.info(f"AgentManager initialized with {len(self._agents)} agents")

    def update(self, delta_time: float, publish_telemetry: bool = True):
        adjusted_delta = delta_time * self._engine.speed_factor

        for agent_id, agent in list(self._agents.items()):
            old_state = agent.state.value

            if (
                publish_telemetry                    # Only publish telemetry if enabled
                and self._enable_llm_agents          # Only if LLM agents are enabled   
                and isinstance(agent, FireBrigade)   # Only FireBrigades can announce
                and self._agent_communication        # Only if communication is enabled
                and agent.state.value != old_state   # Only if state has changed
            ): 
                self._announce_agent_state_changes(agent_id, agent, old_state)
            
            if publish_telemetry and self._agent_communication:
                try:
                    
                    try:
                        current_sector = self._map.find_sector(agent.location)
                    except Exception as e:
                        logger.error(f"[AGENT-STATUS] Failed to find sector for {agent_id}: {e}")
                        continue

                    try:
                        announcement = None
                        try:
                            announcement = self._generate_announcement_non_blocking(agent, current_sector)
                        except Exception as e:
                            logger.debug(f"[AGENT-STATUS] Announcement generation exception for {agent_id}: {type(e).__name__}")
                            pass
                        
                        if announcement and self._agent_communication:
                            try:
                                self._agent_communication.announce_action(
                                    agent_id         = announcement['agent_id'],
                                    action           = "status_update",
                                    target_sector_id = announcement.get('sector'),
                                    location         = announcement.get('location'),
                                    reasoning        = announcement.get('natural_language'),
                                    additional_data={
                                        "natural_language": announcement.get('natural_language'),
                                        "status": announcement.get('status')
                                    }
                                )
                            except Exception as e:
                                logger.debug(f"[AGENT-STATUS] Failed to send announcement for {agent_id}: {e}")
                    except Exception as e:
                        logger.error(f"[AGENT-STATUS] Failed to generate announcement for {agent_id}: {e}")
                        continue
                    

                except Exception as e:
                    logger.debug(f"[AGENT-STATUS] Failed to publish status announcement for {agent_id}: {e}")
            
            '''
            Update agent physics and state
            Update state tasks 
            '''
            event = agent.update_physics(adjusted_delta, self._map)
            # new_state = agent.state.value
            
            if publish_telemetry:
                now = time.time()
                last_telemetry_ts = self._agent_last_telemetry_ts.get(agent_id, 0.0)
                time_since_last = now - last_telemetry_ts
                
                if time_since_last >= self._telemetry_throttle_interval:
                    # Metrics: count position updates for debug logging
                    if self._pos_update_window_start == 0.0:
                        self._pos_update_window_start = now
                    # self._pos_update_count += 1

                    current_sector = self._map.find_sector(agent.location)
                    self._agent_sectors[agent_id] = current_sector
                    self._publish_telemetry(agent, event, current_sector)
                    self._agent_last_telemetry_ts[agent_id] = now


        # if publish_telemetry and self._pos_update_window_start > 0.0:
        #     now = time.time()
        #     window = now - self._pos_update_window_start
        #     if window >= 60.0:  # co minutę
        #         updates_per_sec = self._pos_update_count / window
        #         updates_per_min = updates_per_sec * 60.0
        #         logger.info(
        #             "[AGENT-METRICS] Position updates: %d in %.1fs (%.1f / sec, %.1f / min)",
        #             self._pos_update_count,
        #             window,
        #             updates_per_sec,
        #             updates_per_min,
        #         )
        #         # reset window
        #         self._pos_update_count = 0
        #         self._pos_update_window_start = now
    
    def process_command(self, command: dict):
        agent_id = str(command.get("agentId", ""))
        if not agent_id: return
        
        agent = self._agents.get(agent_id)
        if not agent:
            logger.error(f"[COMMAND] Agent not found: {agent_id}")
            return
        
        try:
            agent.execute_command(command)
        except Exception as e:
            logger.error(f"[COMMAND] Failed to execute command for {agent_id}: {e}")

    def _publish_telemetry(self, agent: Agent, event: dict, sector: Optional[Sector]):
        if not self._message_store: return
        config = get_agent_config(agent)
        agent_id_val = agent.fire_brigade_id if isinstance(agent, FireBrigade) else (agent.forester_patrol_id if isinstance(agent, ForesterPatrol) else agent.agent_id)

        try:
            if isinstance(agent_id_val, str) and agent_id_val.isdigit():
                agent_id_val = int(agent_id_val)
        except Exception:
            pass
        
        s_map = {"idle": "AVAILABLE", "traveling": "TRAVELLING", "executing": ("EXTINGUISHING" if isinstance(agent, FireBrigade) else "PATROLLING"), "returning": "TRAVELLING"}
        state_val = s_map.get(agent.state.value, "AVAILABLE")
        session_id = getattr(self._engine, '_simulation_session_id', None)
        
        # Ensure location is always set - use base_location as fallback
        if agent.location:
            location = {
                "latitude": agent.location.latitude, 
                "longitude": agent.location.longitude
            }
        elif agent.base_location:
            # Fallback to base_location if location is not set
            location = {
                "latitude": agent.base_location.latitude,
                "longitude": agent.base_location.longitude
            }
        else:
            # Last resort: use (0, 0) if neither is available
            logger.warning(f"Agent {agent_id_val} has no location or base_location in _publish_telemetry, using (0,0) as fallback")
            location = {"latitude": 0.0, "longitude": 0.0}
        
        # Handle destination similarly
        if agent.destination:
            destination = {
                "latitude": agent.destination.latitude, 
                "longitude": agent.destination.longitude
            }
        else:
            destination = location  # Use current location as fallback
        
        message = {
            "timestamp": datetime.now().isoformat(),
            "event" : event.get("event", "idle"),
            "location": location,
            "sectorId": sector.sector_id if sector else None,
            "destination": destination,
            "state": state_val,
            config.id_field_name: agent_id_val,
            "type": config.type_name,
            "simulationSessionId": session_id
        }

        self.queue_telemetry(config.telemetry_topic, message)

    def queue_telemetry(self, topic: str, message: dict):
        """Accumulate messages per topic and flush later."""
        if not topic: return
        lst = self._telemetry_batch.setdefault(topic, [])
        lst.append(message)

    def flush_telemetry(self):
        """Send batched telemetry messages once per tick."""
        if not self._message_store:
            self._telemetry_batch.clear()
            return
        from datetime import datetime
        for topic, messages in list(self._telemetry_batch.items()):
            if not messages:
                continue
            batch_msg = {
                "timestamp": datetime.now().isoformat(),
                "batch": messages
            }
            try:
                self._message_store.add_message_to_sent(topic, batch_msg)
            except Exception:
                logger.exception("Error sending telemetry batch for topic %s", topic)
        self._telemetry_batch.clear()

    def get_agent_states(self) -> List[dict]:
        states = []
        ts = datetime.now().isoformat()
        for agent_id, agent in self._agents.items():
            sector = self._agent_sectors.get(agent_id)
            config = get_agent_config(agent)

            s_map = {
                "idle"     : "AVAILABLE", 
                "traveling": "TRAVELLING", 
                "executing": ("EXTINGUISHING" if isinstance(agent, FireBrigade) else "PATROLLING"), 
                "returning": "TRAVELLING"}
            
            destination = {
                "latitude":  agent.destination.latitude, 
                "longitude": agent.destination.longitude
            } if agent.destination else None

            # Ensure location is always set - use base_location as fallback
            if agent.location:
                location = {
                    "latitude": agent.location.latitude, 
                    "longitude": agent.location.longitude
                }
            elif agent.base_location:
                # Fallback to base_location if location is not set
                location = {
                    "latitude": agent.base_location.latitude,
                    "longitude": agent.base_location.longitude
                }
            else:
                # Last resort: use (0, 0) if neither is available
                logger.warning(f"Agent {agent_id} has no location or base_location, using (0,0) as fallback")
                location = {"latitude": 0.0, "longitude": 0.0}

            baseLocation = {
                "latitude": agent.base_location.latitude, 
                "longitude": agent.base_location.longitude
            } if agent.base_location else None


            if isinstance(agent, FireBrigade):
                id_value = agent.fire_brigade_id
            elif isinstance(agent, ForesterPatrol):
                id_value = agent.forester_patrol_id
            else:
                id_value = agent.agent_id

            try:
                if isinstance(id_value, str) and id_value.isdigit():
                    id_value = int(id_value)
            except Exception:
                pass

            states.append({
                "timestamp"          : ts,
                "state"              : s_map.get(agent.state.value, "AVAILABLE"),
                "location"           : location,
                "sectorId"           : sector.sector_id if sector else None,
                "destination"        : destination,
                "baseLocation"       : baseLocation,
                "type"               : config.type_name,
                config.id_field_name : id_value
            })
        return states

    def _announce_agent_state_changes(self, agent_id: str, agent: FireBrigade, old_state: str):
        if not self._agent_communication: return
        curr = agent.state.value

        match (old_state, curr):
            case ("idle", "idle"):
                return
            case ('idle', 'traveling'):
                target = self._map.find_sector(agent.destination)
                self._announce_action(agent_id, "order_received", target.sector_id if target else None, "Moving to task")
            case ('traveling', 'executing'):
                sector = self._agent_sectors.get(agent_id)
                self._announce_action(agent_id, "starting_extinguish", sector.sector_id if sector else None)
            case ('executing', 'returning'):
                sector = self._agent_sectors.get(agent_id)
                self._announce_action(agent_id, "task_complete", sector.sector_id if sector else None)
            case _:
                logger.debug(f"[LLM] No announcement rule for state change {old_state} -> {curr} for agent {agent_id}")



    def _generate_announcement_non_blocking(self, agent: Agent, current_sector: Optional[Sector]) -> Optional[Dict]:
        """
        Generate announcement non-blocking with timeout.
        If LLM call takes too long, immediately use template fallback.
        """
        if not hasattr(agent, '_generate_status_announcement'):
            return None
        
        # Check throttling first (fast check)
        current_time = time.time()
        if hasattr(agent, '_last_status_announcement_time'):
            if current_time - agent._last_status_announcement_time < 1.0:
                return None
        
        # Try to get announcement with timeout
        try:
            future = self._announcement_executor.submit(agent._generate_status_announcement, current_sector)
            announcement = future.result(timeout=self._announcement_timeout)
            return announcement
        except FutureTimeoutError:
            # LLM call took too long (>1s), generate template-based announcement immediately
            # This is expected behavior - not an error
            logger.debug(f"[AGENT-STATUS] LLM timeout for {agent._agent_id} (>{self._announcement_timeout}s), using fast template")
            return self._generate_fast_template_announcement(agent, current_sector)
        except Exception as e:
            # Any other exception - fall back to template (expected for network issues, etc.)
            logger.debug(f"[AGENT-STATUS] Announcement generation failed for {agent._agent_id}: {type(e).__name__}")
            return self._generate_fast_template_announcement(agent, current_sector)
    
    def _generate_fast_template_announcement(self, agent: Agent, current_sector: Optional[Sector]) -> Optional[Dict]:
        """Fast template-based announcement (no LLM, always works)"""
        try:
            import random
            current_time = time.time()
            
            # Update throttle time
            agent._last_status_announcement_time = current_time
            
            sector_id = current_sector.sector_id if current_sector else None
            status_map = {
                "idle": "AVAILABLE",
                "traveling": "TRAVELLING",
                "executing": "EXTINGUISHING" if hasattr(agent, 'fire_brigade_id') else "PATROLLING",
                "returning": "TRAVELLING"
            }
            status = status_map.get(agent._state.value, "AVAILABLE")
            
            # Fast template selection
            templates = {
                "AVAILABLE": ["ready to respond", "available and waiting", "standing by"],
                "TRAVELLING": ["moving to destination", "en route", "traveling"],
                "EXTINGUISHING": ["fighting fires", "extinguishing", "fire suppression"],
                "PATROLLING": ["patrolling area", "on patrol", "monitoring"]
            }
            
            action = random.choice(templates.get(status, templates["AVAILABLE"]))
            nl_response = f"Hey, Agent {agent._agent_id}, my status is {status}, I'm {action}"
            if sector_id is not None:
                nl_response += f", {{SECTOR: {sector_id}, STATUS: {status}}}"
            
            return {
                "timestamp": datetime.now().isoformat(),
                "agent_id": agent._agent_id,
                "natural_language": nl_response,
                "sector": sector_id,
                "status": status,
                "location": {
                    "latitude": agent._location.latitude,
                    "longitude": agent._location.longitude
                }
            }
        except Exception as e:
            logger.debug(f"[AGENT-STATUS] Fast template failed for {agent._agent_id}: {e}")
            return None

    def _announce_action(self, agent_id: str, action: str, target_sector_id: Optional[int] = None, reasoning: Optional[str] = None):
        if not self._agent_communication: return
        agent = self._agents.get(agent_id)
        if agent:
            self._agent_communication.announce_action(agent_id, action, target_sector_id, {"latitude": agent.location.latitude, "longitude": agent.location.longitude}, reasoning)
