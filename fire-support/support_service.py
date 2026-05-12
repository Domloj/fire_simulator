"""
Refactored Support Service - Main orchestration module.

Coordinates state management, RabbitMQ communication, and MCTS workers
to generate firefighting recommendations.
"""

import logging
import threading
import time
import json
import os
from datetime import datetime
from typing import Dict, Optional, List, Set, Tuple

from state_manager import StateManager
from rabbitmq_handler import RabbitMQHandler
from mcts_worker import MCTSWorkerPool
from state_converter import StateConverter
from contracts import RecommendationMessage, RecommendedAction, validate_recommendation_message
from llm.llm_client import LLMClient
from llm.agent_communication import AgentCommunication
from llm.message_store_adapter import MessageStoreAdapter
from llm.topics import TopicRegistry
from llm.config import LLMConfig, get_config

logger = logging.getLogger(__name__)

class SupportService:
    """Main service orchestrating recommendation generation"""
    
    def __init__(
        self, 
        num_workers: int = None, 
        llm_config: Optional[LLMConfig] = None
    ):
        self.state_manager = StateManager()
        self.rabbitmq = RabbitMQHandler()
        self.worker_pool = MCTSWorkerPool(num_workers)
        
        if llm_config is None:
            llm_config = get_config()
        
        self._llm_config = llm_config
        
        use_llm = llm_config.use_llm_coordination
        self._llm_client = None
        self._message_store_adapter = None
        self._agent_communication = None
        
        import os
        logger.info(f"[LLM-INIT] use_llm_coordination={llm_config.use_llm_coordination}, recommendation_mode={llm_config.recommendation_mode}")
        logger.info(f"[LLM-INIT] LLM_ENABLED check: {os.getenv('LLM_ENABLED', 'not set')}")
        logger.info(f"[LLM-INIT] use_llm={use_llm}, is_llm_enabled={llm_config.is_llm_enabled}")
        
        if use_llm:
            try:
                logger.info("[LLM-INIT] Initializing LLM client...")
                self._llm_client = LLMClient(
                    model=llm_config.llm_model,
                    api_key=llm_config.llm_api_key,
                    base_url=llm_config.llm_base_url
                )
                logger.info("[LLM-INIT] LLM client initialized successfully")
            except Exception as e:
                logger.error(f"[LLM-INIT] Failed to initialize LLM client: {e}", exc_info=True)
                self._llm_client = None
                use_llm = False 
            
            if self._llm_client:
                try:
                    logger.info("[LLM-INIT] Initializing message store adapter...")
                    self._message_store_adapter = MessageStoreAdapter(self.rabbitmq)
                    logger.info("[LLM-INIT] Message store adapter initialized successfully")
                except Exception as e:
                    logger.error(f"[LLM-INIT] Failed to initialize message store adapter: {e}", exc_info=True)
                    self._message_store_adapter = None
                
                if self._message_store_adapter:
                    try:
                        logger.info("[LLM-INIT] Initializing agent communication...")
                        self._agent_communication = AgentCommunication(self._message_store_adapter)
                        logger.info("[LLM-INIT] Agent communication initialized successfully")
                    except Exception as e:
                        logger.error(f"[LLM-INIT] Failed to initialize agent communication: {e}", exc_info=True)
                        self._agent_communication = None

        self._last_recommendations: Optional[Dict] = None
        self._last_recommendations_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._consumer_threads: List[threading.Thread] = []
        self._recommendation_thread: Optional[threading.Thread] = None
        self._recommendation_interval = 1.0  # Interval between recommendation generation attempts (reduced to 1.0s for very fast updates)
        self._last_sector_states: Dict[int, float] = {}  # sector_id -> fire_level
        self._sector_change_threshold = 0.5  # Lower threshold for faster triggering (reduced to 0.5 for very sensitive detection)
        self._last_published_recommendations: Optional[Dict] = None
        self._recommendation_cooldown = 0.8  # Publish at most 1 recommendation per 0.8 seconds (reduced for very responsive updates)
        self._last_recommendation_time = 0.0
        self._travelling_units: Set[Tuple[str, int]] = set() 
        self._last_prediction_score = -float('inf')
        self._stability_threshold = 0.98
        self._reward_improvement_threshold = 0.5  
        self._llm_call_times: List[float] = []  
        self._llm_rate_limit = 10.0
        self._max_llm_calls_per_minute = 6 
        self._last_chat_response_time = 0.0
        self._chat_cooldown = llm_config.agent_llm_cooldown if hasattr(llm_config, 'agent_llm_cooldown') else 30
        self._pending_chat_requests: List[Dict] = []
        self._chat_lock = threading.Lock()

        self._recalculation_lock = threading.Lock()
        self._recalculation_needed = threading.Event()
        
        logger.info("=" * 80)
        logger.info("SUPPORT SERVICE INITIALIZATION")
        logger.info("=" * 80)
        logger.debug(f"Recommendation Mode: {llm_config.recommendation_mode}")
        logger.debug(f"Agent Decision Mode: {llm_config.agent_decision_mode}")
        logger.debug(f"LLM Coordination Enabled: {llm_config.use_llm_coordination}")
        logger.debug(f"Agent LLM Enabled: {llm_config.use_agent_llm}")
        logger.debug(f"LLM Model: {llm_config.llm_model}")
        logger.debug(f"LLM API Key Configured: {'YES' if llm_config.llm_api_key else 'NO'}")
        logger.debug(f"LLM Base URL: {llm_config.llm_base_url or 'default'}")
        
        if self._llm_client:
            logger.debug("[LLM-AGENT] LLM Client Status:")
            logger.debug(f" API Key: {'SET' if self._llm_client.api_key else 'NOT SET'}")
        else:
            logger.debug(" NOT INITIALIZED (LLM coordination disabled)")
        
        if self._agent_communication:
            logger.debug("-" * 80)
            logger.debug("[LLM-AGENT] Agent Communication Status:")
            logger.debug(f" MessageStore Adapter: {'YES' if self._message_store_adapter else 'NO'}")
            logger.debug(f" RabbitMQ Connection: {'YES' if self.rabbitmq else 'NO'}")
        else:
            logger.debug("-" * 80)
            logger.debug("[LLM-AGENT] Agent Communication Status:")
            logger.debug("  NOT INITIALIZED")
            
    def start(self, config: Optional[Dict] = None):
        """
        Start the support service.
        
        Args:
            config: Optional forest configuration dictionary
        """
        if config:
            self.state_manager.set_config(config)
            logger.info("Configuration provided at startup")
        else:
            logger.info("No config provided, will wait for config from RabbitMQ")
        
        logger.info("Starting support service...")
        self._stop_event.clear()
        
        self.state_manager.clear_state()
        self._last_published_recommendations = None
        self._last_recommendation_time = 0.0
        self._last_prediction_score = -float('inf')
        self._travelling_units.clear()
        try:
            if self._llm_config and self._should_use_llm_mode(None):
                logger.info("LLM-ONLY mode detected – skipping MCTS worker pool start")
            else:
                self.worker_pool.start()
        except Exception as e:
            logger.error(f"Error starting MCTS worker pool: {e}", exc_info=True)
        try:
            self._start_consumers()
        except Exception as e:
            logger.error(f"Error starting consumers: {e}", exc_info=True)
            raise
        
        try:
            self._start_recommendation_thread()
        except Exception as e:
            logger.error(f"Error starting recommendation thread: {e}", exc_info=True)
            raise
        
        if self._llm_client:
            try:
                self._test_llm_initialization()
            except Exception as e:
                logger.error(f"Error in LLM initialization test: {e}", exc_info=True)
        
        logger.info("Support service started")
    
    def stop(self):
        """Stop the support service with full cleanup"""
        logger.info("Stopping support service...")
        self._stop_event.set()
        self._recalculation_needed.set()
        
        if self._recommendation_thread and self._recommendation_thread.is_alive():
            logger.info("Waiting for recommendation thread to stop...")
            try:
                self._recommendation_thread.join(timeout=5.0)
                if self._recommendation_thread.is_alive():
                    logger.warning("Recommendation thread did not stop within timeout")
                else:
                    logger.info("Recommendation thread stopped")
            except Exception as e:
                logger.error(f"Error waiting for recommendation thread: {e}", exc_info=True)
        
        logger.info("Stopping consumer threads...")
        for thread in self._consumer_threads:
            if thread and thread.is_alive():
                try:
                    logger.debug(f"Waiting for consumer thread {thread.name} to stop...")
                    thread.join(timeout=5.0)
                    if thread.is_alive():
                        logger.warning(f"Consumer thread {thread.name} did not stop within timeout")
                    else:
                        logger.debug(f"Consumer thread {thread.name} stopped")
                except Exception as e:
                    logger.error(f"Error waiting for consumer thread {thread.name}: {e}", exc_info=True)
        
        self._consumer_threads.clear()
        self._recommendation_thread = None
        
        logger.info("Stopping worker pool...")
        try:
            if self.worker_pool:
                self.worker_pool.stop()
        except Exception as e:
            logger.error(f"Error stopping worker pool: {e}", exc_info=True)
        
        with self._chat_lock:
            self._pending_chat_requests.clear()
        
        self._llm_call_times.clear()
        
        if self._agent_communication:
            try:
                if hasattr(self._agent_communication, 'clear_state'):
                    self._agent_communication.clear_state()
            except Exception as e:
                logger.debug(f"Error clearing agent communication state: {e}")
        
        try:
            self.state_manager.clear_state()
        except Exception as e:
            logger.error(f"Error clearing state manager: {e}", exc_info=True)
        
        self._last_published_recommendations = None
        self._last_recommendations = None
        self._last_recommendation_time = 0.0
        self._last_prediction_score = -float('inf')
        self._travelling_units.clear()
        self._last_sector_states.clear()

        try:
            self.rabbitmq.purge_queues([
                "support_data_aggregated",
                "simulation_recommendations",
                "support_agent_position",
                "support_llm_requests",
                "support_llm_propositions",
                "support_llm_propositions_responses",
            ])
        except Exception as e:
            logger.error(f"Error purging RabbitMQ queues: {e}", exc_info=True)
        
        logger.info("Closing RabbitMQ connections...")
        try:
            self.rabbitmq.close()
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connections: {e}", exc_info=True)
        
        logger.info("Support service stopped and cleaned up")
    
    def _start_consumers(self):
        """Start RabbitMQ consumers"""

        thread = self.rabbitmq.start_consumer(
            queue_name  = 'support_data_aggregated',
            routing_key = 'support.data.aggregated',
            callback    = self._handle_state_message,
            stop_event  = self._stop_event
        )
        self._consumer_threads.append(thread)
        
        thread = self.rabbitmq.start_consumer(
            queue_name  = 'simulation_recommendations',
            routing_key = 'simulation.recommendations',
            callback    = self._handle_simulation_recommendation,
            stop_event  = self._stop_event
        )
        self._consumer_threads.append(thread)

        thread = self.rabbitmq.start_consumer(
            queue_name  = 'support_agent_position',
            routing_key = 'agent_position',
            callback    = self._handle_agent_position_message,
            stop_event  = self._stop_event
        )
        self._consumer_threads.append(thread)
        
        if self._llm_config and self._llm_config.use_agent_llm and self._agent_communication:
            try:
                thread = self._agent_communication.setup_consumer(self._stop_event, callback=self._handle_agent_announcement)
                if thread:
                    self._consumer_threads.append(thread)
                    logger.info("[LLM-CONSUMER] Started consumer for agent announcements")
            except Exception as e:
                logger.error(f"[LLM-CONSUMER] Failed to start agent announcements consumer: {e}", exc_info=True)
        
        if self._llm_config and self._llm_config.enable_agent_chat:
            thread = self.rabbitmq.start_consumer(
                queue_name  = 'support_llm_requests',
                routing_key = 'support.llm.requests',
                callback    = self._handle_llm_chat_request,
                stop_event  = self._stop_event
            )
            self._consumer_threads.append(thread)
            logger.debug("Started consumer for Strategic LLM Chat (support.llm.requests)")
            
            # LLM Proposition Handling
            thread = self.rabbitmq.start_consumer(
                queue_name  = "support_llm_propositions",
                routing_key = "support.llm.propositions",
                callback    = self._handle_llm_proposition,
                stop_event  = self._stop_event
            )
            self._consumer_threads.append(thread)
            logger.debug("Started consumer for Agent Propositions (support.llm.propositions)")
            
            # LLM Proposition Response Handling
            thread = self.rabbitmq.start_consumer(
                queue_name  = "support_llm_propositions_responses",
                routing_key = "support.llm.propositions.responses",
                callback    = self._handle_proposition_response,
                stop_event  = self._stop_event
            )
            self._consumer_threads.append(thread)
            logger.debug("Started consumer for Proposition Responses (support.llm.propositions.responses)")

    def _handle_agent_position_message(self, message: Dict):
        """Obsługa eventu agent_position (dedykowana kolejka pozycji agentów)"""
        try:
            if message.get('type') == 'agent_position' and 'data' in message:
                for agent in message['data']:
                    self.state_manager.update_agent_position(agent)
        except Exception as e:
            logger.error(f"Error handling agent_position message: {e}", exc_info=True)
    
    def _handle_agent_announcement(self, message: Dict):
        """Handle incoming agent announcement messages"""
        try:
            if not self._llm_config or not self._llm_config.use_agent_llm:
                return
            
            agent_id = message.get('agent_id')
            action = message.get('action')
            natural_language = message.get('natural_language') or message.get('reasoning')
            sector_id = message.get('target_sector_id') or message.get('sector')
            status = message.get('status')
            
            if not agent_id:
                return
            
            logger.debug(f"[AGENT-ANNOUNCEMENT] Received from {agent_id}: {natural_language[:50] if natural_language else action}")
            
            if self._agent_communication:
                with self._chat_lock:
                    self._pending_chat_requests.append({
                        "agent_id": agent_id,
                        "natural_language": natural_language,
                        "sector": sector_id,
                        "status": status,
                        "action": action,
                        "timestamp": time.time()
                    })
                    if len(self._pending_chat_requests) > 50:
                        self._pending_chat_requests.pop(0)
                
                current_time = time.time()
                time_since_last = current_time - self._last_chat_response_time
                
                if len(self._pending_chat_requests) >= 5 or time_since_last >= self._chat_cooldown:
                    threading.Thread(
                        target=self._generate_llm_predictions_from_announcements,
                        daemon=True
                    ).start()
                    logger.debug(f"[AGENT-ANNOUNCEMENT] Triggered prediction generation ({len(self._pending_chat_requests)} announcements)")
                
        except Exception as e:
            logger.error(f"Error handling agent announcement: {e}", exc_info=True)
    
    def _handle_state_message(self, message: Dict):
        """Handle incoming state update or configuration message"""
        try:
            if 'location' in message and ('forestId' in message or 'forestName' in message):
                logger.info(f"Received configuration message for forestId: {message.get('forestId')} - resetting state")
                self.state_manager.clear_state()
                self.state_manager.set_config(message)

                self._last_published_recommendations = None
                self._last_prediction_score = -float('inf')
                self._last_recommendation_time = 0.0
                self._travelling_units.clear()
                return
            
            msg_forest_id = message.get('forestId')
            msg_session_id = message.get('simulationSessionId')
            current_forest_id = self.state_manager.forest_id
            current_session_id = self.state_manager.simulation_session_id
            
            if current_session_id:
                if not msg_session_id:
                    logger.debug("Ignoring aggregated update missing simulationSessionId")
                    return
                if msg_session_id != current_session_id:
                    logger.debug(f"Ignoring aggregated update for old simulationSessionId: {msg_session_id}")
                    return
                
            if msg_forest_id and current_forest_id and msg_forest_id != current_forest_id:
                logger.debug(f"Ignoring aggregated update for old forestId: {msg_forest_id}")
                return

            sector_changes_detected = False
            if 'sectors' in message:
                sectors = message.get('sectors', {})
                sectors_list = sectors.values() if isinstance(sectors, dict) else sectors if isinstance(sectors, list) else []
                
                for sector_state in sectors_list:
                    sector_id = sector_state.get('sectorId')
                    if sector_id is None:
                        continue
                    
                    state_obj = sector_state.get('state', {})
                    if isinstance(state_obj, dict):
                        current_fire_level = state_obj.get('fireLevel', 0)
                        last_fire_level = self._last_sector_states.get(sector_id, 0)
                        
                        if abs(current_fire_level - last_fire_level) >= self._sector_change_threshold:
                            sector_changes_detected = True
                            self._last_sector_states[sector_id] = current_fire_level
            
            if 'sectors' in message:
                sectors = message.get('sectors', {})
                sectors_list = sectors.values() if isinstance(sectors, dict) else sectors if isinstance(sectors, list) else []
                
                for sector in sectors_list:
                    self.state_manager.update_sector_state(sector)
                    sector_id = sector.get('sectorId')
                    if sector_id is not None:
                        state_obj = sector.get('state', {})
                        if isinstance(state_obj, dict):
                            self._last_sector_states[sector_id] = state_obj.get('fireLevel', 0)
            
            if 'fireBrigades' in message:
                fire_brigades = message.get('fireBrigades', {})
                if isinstance(fire_brigades, list):
                    for brigade in fire_brigades:
                        self.state_manager.update_fire_brigade_state(brigade)
                        self._update_unit_travelling_status(brigade, 'fireBrigade')
                elif isinstance(fire_brigades, dict):
                    for brigade in fire_brigades.values():
                        self.state_manager.update_fire_brigade_state(brigade)
                        self._update_unit_travelling_status(brigade, 'fireBrigade')
                else:
                    logger.warning(f"Fire brigades in unexpected format: {type(fire_brigades)}")
            
            if 'foresterPatrols' in message:
                forester_patrols = message.get('foresterPatrols', {})
                if isinstance(forester_patrols, list):
                    for patrol in forester_patrols:
                        self.state_manager.update_forester_patrol_state(patrol)
                        self._update_unit_travelling_status(patrol, 'foresterPatrol')
                elif isinstance(forester_patrols, dict):
                    for patrol in forester_patrols.values():
                        self.state_manager.update_forester_patrol_state(patrol)
                        self._update_unit_travelling_status(patrol, 'foresterPatrol')
                else:
                    logger.warning(f"Forester patrols in unexpected format: {type(forester_patrols)}")
            
            if sector_changes_detected:
                logger.debug("Significant sector state change detected, triggering recommendation")
                self._recalculation_needed.set()
                    
        except Exception as e:
            logger.error(f"Error handling state message: {e}", exc_info=True)
    
    def _handle_simulation_recommendation(self, message: Dict):
        """Handle recommendation from simulation (for forwarding/logging)"""
        try:
            logger.debug(f"Received simulation recommendation: {message}")
        except Exception as e:
            logger.error(f"Error handling simulation recommendation: {e}", exc_info=True)
    
    def _handle_llm_chat_request(self, message: Dict):
        """
        Handle incoming BrigadeOrder from agents for strategic chat analysis.
        Buffers requests and triggers analysis with cooldown.
        """
        if not self._llm_config.enable_agent_chat or not self._llm_client:
            return
            
        try:
            with self._chat_lock:
                self._pending_chat_requests.append(message)
            
            if len(self._pending_chat_requests) % 5 == 0:
                logger.debug(f"[CHAT] Buffered {len(self._pending_chat_requests)} chat requests")
                
            threading.Thread(target=self._perform_strategic_chat_analysis, daemon=True).start()
            
        except Exception as e:
            logger.error(f"Error buffering LLM chat request: {e}")

    def _perform_strategic_chat_analysis(self):
        """Perform strategic analysis of buffered requests using LLM"""
        if not self._chat_lock.acquire(blocking=False):
            return
            
        try:
            current_time = time.time()
            time_to_wait = self._chat_cooldown - (current_time - self._last_chat_response_time)
            
            if time_to_wait > 0:
                time.sleep(time_to_wait)
            
            with self._chat_lock:
                requests = list(self._pending_chat_requests)
                self._pending_chat_requests.clear()
            
            if not requests:
                return
                
            
            sectors, fire_brigades, forester_patrols = self.state_manager.get_state_copy()
            active_fires = [s for s in sectors.values() if s.get('state', {}).get('fireLevel', 0) > 0]
            
            agent_actions = []
            for req in requests[-5:]:  # Last 5 orders
                agent_id = req.get('agentId', 'Unknown')
                description = req.get('description', '')
                agent_actions.append(f"- Agent {agent_id}: {description}")
            
            context = {
                "active_fires_count": len(active_fires),
                "fire_brigades_count": len(fire_brigades),
                "recent_agent_orders": agent_actions,
                "world_summary": f"{len(active_fires)} fires active across {len(sectors)} sectors"
            }
            
            system_prompt = """You are the Strategic Fire Coordinator. Your role:
1. Monitor all agent actions
2. Identify tactical issues (overcrowding, undefended sectors, etc.)
3. Provide detailed, constructive strategic guidance
4. Reference specific sectors and units in your analysis
IMPORTANT: Be specific about what you observe and why action is needed."""
            
            context_str = "\n".join(agent_actions) if agent_actions else "No recent agent actions"
            user_prompt = f"""SITUATION ANALYSIS:
Recent Agent Communications:
{context_str}

Active Fire Events: {len(active_fires)} sectors burning
Total Deployed Units: {len(fire_brigades)} brigades

YOUR TASK:
Analyze these actions and provide tactical guidance:
- What is working well?
- What needs adjustment?
- Are sectors properly defended?
- Any unit clustering issues?

Respond with a detailed strategic observation that references specific sectors and proposes adjustments if needed."""
            
            import json
            response = self._llm_client.complete(user_prompt, system_prompt)
            try:
                proposition_data = {
                    "proposition": response,
                    "reasoning": "Strategic analysis and coordination",
                    "affectedAgents": []
                }
                
                chat_response = {
                    "timestamp": datetime.now().isoformat(),
                    "type": "LLM_proposition",
                    "content": proposition_data,
                    "source": "Strategic_Coordinator"
                }
                
                self.rabbitmq.publish_message(chat_response, routing_key='support.llm.responses')
                self._last_chat_response_time = time.time()
                
            except Exception as e:
                logger.error(f"Error parsing strategic LLM response: {e}")
                
        finally:
            self._chat_lock.release()

    def _start_recommendation_thread(self):
        """Start thread that periodically generates recommendations or responds to triggers"""
        def recommendation_loop():
            logger.info("Recommendation loop started")
            if not self._stop_event.is_set():
                self._generate_recommendations()
            
            while not self._stop_event.is_set():
                try:
                    timeout_remaining = self._recommendation_interval
                    triggered = False
                    
                    while timeout_remaining > 0 and not self._stop_event.is_set():
                        chunk_timeout = min(0.5, timeout_remaining)  # Check stop_event every 0.5s
                        triggered = self._recalculation_needed.wait(timeout=chunk_timeout)
                        if triggered:
                            break
                        timeout_remaining -= chunk_timeout
                    
                    if not self._stop_event.is_set():
                        self._generate_recommendations()
                        
                    if triggered:
                        self._recalculation_needed.clear()
                        
                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error(f"Error in recommendation loop: {e}", exc_info=True)
            
            logger.info("Recommendation loop stopped")
        
        self._recommendation_thread = threading.Thread(target=recommendation_loop, daemon=False, name="RecommendationThread")
        self._recommendation_thread.start()
        logger.info("Started recommendation generation thread")
    
    def _generate_recommendations(self):
        """Generate recommendations using MCTS"""
        from simulation.agent_state import AGENT_STATE
        
        if not self._recalculation_lock.acquire(blocking=False):
            logger.debug("Recommendation already in progress, skipping concurrent call")
            return
            
        try:
            sectors, fire_brigades, forester_patrols = self.state_manager.get_state_copy()
            state_age = time.time() - self.state_manager.last_update_time
            
            logger.debug(f"Generating recommendations: sectors={len(sectors)}, "
                        f"fire_brigades={len(fire_brigades)}, forester_patrols={len(forester_patrols)}, "
                        f"state_age={state_age:.2f}s")
            
            if state_age > 5.0:
                logger.warning(f"State is stale: {state_age:.2f}s old. Recommendations may be based on outdated data.")
            
            if not sectors or not fire_brigades:
                logger.debug("Insufficient state for recommendations")
                return
            
            config = self.state_manager.get_config()
            if not config:
                logger.debug("No configuration available")
                return
            
            forest_map = StateConverter.state_to_forest_map(
                sectors, fire_brigades, forester_patrols, config
            )
            if not forest_map:
                logger.warning("Failed to convert state to ForestMap")
                return
            
            forest_map.update_extinguish_levels()
            
            all_sectors = [s for row in forest_map.sectors for s in row]
            sectors_with_fire = [s for s in all_sectors if s.fire_level > 0]
            logger.debug(f"ForestMap built: {len(all_sectors)} sectors, {len(sectors_with_fire)} with fire. "
                        f"Top fire levels: {[s.fire_level for s in sorted(sectors_with_fire, key=lambda x: x.fire_level, reverse=True)[:5]]}")

            is_llm_only_mode = self._should_use_llm_mode(forest_map)
            
            if is_llm_only_mode:
                logger.info("[MODE] Running in LLM-ONLY mode - Skipping MCTS")
                mcts_result = None
                recommended_actions = []
                current_score = 0
            else:
                mcts_result = self.worker_pool.submit_task(forest_map, timeout=10.0)
                recommended_actions = []
                mcts_reasoning = ""
                current_score = -float('inf')
            
                if mcts_result:
                    recommendations = mcts_result.get('actions', [])
                    mcts_reasoning = mcts_result.get('reasoning', "")
                    current_score = mcts_result.get('score', -float('inf'))
                    recommended_actions = self._convert_recommendations(
                        recommendations, forest_map, mcts_reasoning
                    )
            
            min_target_recommendations = max(5, len(forest_map.fireBrigades))
            
            if is_llm_only_mode or (self._llm_client and len(recommended_actions) < min_target_recommendations):
                if is_llm_only_mode:
                    logger.debug(f"[LLM-GEN] Generating distinct LLM recommendations for ALL available agents (target: {min_target_recommendations})")
                    llm_recommendations_mcts = self._generate_llm_recommendations(
                        forest_map, 
                        min_recommendations=min_target_recommendations, # Generate more recommendations
                        force_all=True
                    )
                else:
                    logger.debug(f"[LLM-FORCE] Only {len(recommended_actions)} MCTS recommendations, "
                            f"generating LLM-driven recommendations to reach minimum of {min_target_recommendations}")
                    llm_recommendations_mcts = self._generate_llm_recommendations(forest_map, min_recommendations=min_target_recommendations)
                
                if llm_recommendations_mcts:
                    llm_recommendations_actions = self._convert_recommendations(
                        llm_recommendations_mcts, forest_map, "LLM-generated recommendations"
                    )
                    
                    existing_unit_ids = {a['unitId'] for a in recommended_actions}
                    for llm_rec in llm_recommendations_actions:
                        if llm_rec['unitId'] not in existing_unit_ids:
                            recommended_actions.append(llm_rec)
                            existing_unit_ids.add(llm_rec['unitId'])
                
                logger.debug(f"[LLM-FORCE] Total recommendations after LLM generation: {len(recommended_actions)}")
            
            if not recommended_actions:
                if self._llm_client:
                    logger.debug("[LLM-FORCE] No recommendations from MCTS, forcing LLM generation of at least 1 recommendation")
                    llm_recommendations_mcts = self._generate_llm_recommendations(forest_map, min_recommendations=1)
                    if llm_recommendations_mcts:
                        llm_recommendations_actions = self._convert_recommendations(
                            llm_recommendations_mcts, forest_map, "LLM-generated recommendations (fallback)"
                        )
                        recommended_actions.extend(llm_recommendations_actions)
                
                if not recommended_actions:
                    # Check if there are any active fires
                    all_sectors = [s for row in forest_map.sectors for s in row]
                    sectors_with_fire = [s for s in all_sectors if s.fire_level > 0]
                    if not sectors_with_fire:
                        logger.info("No valid recommendations - no active fires detected (this is expected)")
                    else:
                        logger.warning(f"No valid recommendations after all attempts (but {len(sectors_with_fire)} sectors have fires)")
                    return
            
            if self._agent_communication and self._llm_client:
                recommended_actions = self._coordinate_with_agents(recommended_actions, forest_map)
                
                if not hasattr(self, '_last_prediction_time'):
                    self._last_prediction_time = 0.0
                
                current_time = time.time()
                if current_time - self._last_prediction_time >= 5.0:  # Every 5 seconds
                    try:
                        self._generate_llm_predictions_from_announcements()
                        self._last_prediction_time = current_time
                    except Exception as e:
                        logger.error(f"Error in prediction generation: {e}", exc_info=True)
        
            stable_actions = self._filter_travelling_units(recommended_actions, forest_map=forest_map)
            
            min_target_actions = max(5, len([a for a in forest_map.fireBrigades if a._state == AGENT_STATE.AVAILABLE]))
            
            if self._llm_client and len(stable_actions) < min_target_actions:
                logger.debug(f"[LLM-FORCE] Only {len(stable_actions)} stable actions, ensuring at least {min_target_actions} for publication")
                if len(recommended_actions) > len(stable_actions):
                    additional = [a for a in recommended_actions if a not in stable_actions]
                    stable_actions.extend(additional[:min_target_actions - len(stable_actions)])
            
            if not stable_actions:
                logger.debug("All recommendations filtered out (units already travelling)")
                if self._llm_client and recommended_actions:
                    logger.debug("[LLM-FORCE] Forcing publication of at least 1 recommendation despite filtering")
                    stable_actions = recommended_actions[:1]
                else:
                    return
            
            current_time = time.time()
            time_since_last = current_time - self._last_recommendation_time
            if time_since_last < self._recommendation_cooldown:
                logger.debug(f"Skipping recommendation update (cooldown: {self._recommendation_cooldown}s, "
                           f"elapsed: {time_since_last:.2f}s)")
                return
            
            is_similar = self._recommendations_are_similar(stable_actions)
            score_improvement = current_score - self._last_prediction_score
            state_age = time.time() - self.state_manager.last_update_time
            
            if self._last_published_recommendations and is_similar:
                if score_improvement < -self._reward_improvement_threshold:  
                    logger.info(f"New recommendations worse (score: {current_score:.2f} vs {self._last_prediction_score:.2f}), "
                               f"keeping previous recommendations")
                    return
                elif score_improvement < 0 and state_age < 3.0:  # New is slightly worse and state is recent
                    logger.debug(f"New recommendations slightly worse (score: {current_score:.2f} vs {self._last_prediction_score:.2f}), "
                               f"keeping previous recommendations")
                    return
            
            if is_similar and score_improvement < self._reward_improvement_threshold:
                if state_age < 3.0:  # Reduced from 5.0 to 3.0 for faster refresh
                    logger.debug(f"Recommendations similar and improvement ({score_improvement:.2f}) "
                               f"below threshold ({self._reward_improvement_threshold}), skipping update")
                    return
                else:
                    logger.info(f"Forcing recommendation update despite similarity (state age: {state_age:.2f}s > 3s)")
            
            recommendation_message: RecommendationMessage = {
                "timestamp": current_time,
                "recommendedActions": stable_actions,
                "priority": "HIGH"
            }
            
            with self._last_recommendations_lock:
                self._last_recommendations = recommendation_message
            
            self._update_travelling_units(stable_actions)
            self._last_published_recommendations = {a['unitId']: a for a in stable_actions}
            self._last_recommendation_time = current_time
            self._last_prediction_score = current_score
            
            rec_parts = []
            for action in stable_actions:
                unit_id = action['unitId']
                sector_id = action['sectorId']
                unit_type = action['unitType']
                mv = 'EX' if unit_type == 'fireBrigade' else 'PT'
                rec_parts.append(f"FB_{unit_id}. {mv}->{sector_id}")
            if rec_parts:
                logger.info(f"REC: {', '.join(rec_parts)}")
            
            success = self.rabbitmq.publish_recommendation(recommendation_message)
            if not success:
                logger.error(f"Failed to publish {len(stable_actions)} recommendations to RabbitMQ")
            else:
                logger.info(f"Published {len(stable_actions)} stable recommendations")
                
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}", exc_info=True)
        finally:
            self._recalculation_lock.release()
    
    def _convert_recommendations(
        self,
        recommendations: List[tuple],
        forest_map,
        reasoning: str = ""
    ) -> List[RecommendedAction]:
        """
        Convert MCTS recommendations (agent_idx, sector_id) to RecommendedAction format.
        Filters out only EXECUTING/EXTINGUISHING brigades.
        Includes AVAILABLE and TRAVELLING brigades (travelling can be redirected).
        
        Args:
            recommendations: List of (agent_idx, sector_id) tuples from MCTS
            forest_map: ForestMap object with agents
            reasoning: Base reasoning from MCTS
        
        Returns:
            List of RecommendedAction dicts
        """
        from simulation.fire_brigades.fire_brigade import FireBrigade
        from simulation.forester_patrols.forester_patrol import ForesterPatrol
        from simulation.agent_state import AGENT_STATE
        
        fire_brigade_list = forest_map.fireBrigades
        forester_patrol_list = getattr(forest_map, "foresterPatrols", [])
        num_fire_brigades = len(fire_brigade_list)
        num_forester_patrols = len(forester_patrol_list)
        
        recommended_actions: List[RecommendedAction] = []
        fire_brigade_count = 0
        forester_patrol_count = 0
        skipped_busy = 0
        
        for agent_idx, sector_id in recommendations:
            try:
                sector_id = int(sector_id)
            except (ValueError, TypeError):
                continue
            
            if 0 <= agent_idx < num_fire_brigades:
                brigade = fire_brigade_list[agent_idx]
                if not isinstance(brigade, FireBrigade):
                    continue
                
                if brigade._state == AGENT_STATE.EXECUTING:
                    skipped_busy += 1
                    continue
                
                try:
                    unit_id = int(brigade.fire_brigade_id)
                except (ValueError, TypeError):
                    continue
                
                sector = forest_map.get_sector(sector_id) if hasattr(forest_map, 'get_sector') else None
                fire_level = sector.fire_level if sector else 0
                description = f"Extinguish sector {sector_id}"
                if fire_level > 50:
                    description += " - high fire level"
                elif fire_level > 20:
                    description += " - moderate fire"
                
                recommended_actions.append({
                    "unitId": unit_id,
                    "sectorId": sector_id,
                    "unitType": "fireBrigade",
                    "action": "EXTINGUISH",  # Explicitly set action for the simulation engine
                    "description": description,
                    "priority": int(fire_level),  # Higher fire level = higher priority
                    "reasoning": reasoning
                })
                fire_brigade_count += 1
            
            elif num_fire_brigades <= agent_idx < num_fire_brigades + num_forester_patrols:
                patrol_idx = agent_idx - num_fire_brigades
                if patrol_idx >= len(forester_patrol_list):
                    continue
                
                patrol = forester_patrol_list[patrol_idx]
                if not isinstance(patrol, ForesterPatrol):
                    continue
                
                try:
                    unit_id = int(patrol.forester_patrol_id)
                except (ValueError, TypeError):
                    continue
                
                if patrol._state == AGENT_STATE.EXECUTING:
                    skipped_busy += 1
                    continue
                
                recommended_actions.append({
                    "unitId": unit_id,
                    "sectorId": sector_id,
                    "unitType": "foresterPatrol",
                    "action": "PATROL",  # Explicitly set action
                    "description": f"Patrol sector {sector_id}",
                    "priority": 1,  # Lower priority for patrols
                    "reasoning": reasoning
                })
                forester_patrol_count += 1
        
        if skipped_busy > 0:
            logger.debug(f"Filtered out {skipped_busy} busy units from recommendations")
        
        return recommended_actions
    
    def _filter_travelling_units(self, recommended_actions: List[RecommendedAction], forest_map=None) -> List[RecommendedAction]:
        """
        Filter out units that are already travelling to prevent rapid recommendation changes.
        Also checks actual agent state from forest_map if available.
        
        Returns:
            Filtered list of recommendations excluding units already travelling
        """
        filtered = []
        skipped = 0
        skipped_by_state = 0
        
        for action in recommended_actions:
            unit_key = (action['unitType'], action['unitId'])
            unit_id = action['unitId']
            unit_type = action['unitType']
            
            if forest_map:
                try:
                    if unit_type == 'fireBrigade':
                        brigade = next((b for b in forest_map.fireBrigades if int(b.fire_brigade_id) == int(unit_id)), None)
                        if brigade:
                            from simulation.agent_state import AGENT_STATE
                            if brigade._state == AGENT_STATE.EXECUTING:
                                skipped_by_state += 1
                                continue
                    elif unit_type == 'foresterPatrol':
                        patrol = next((p for p in getattr(forest_map, 'foresterPatrols', []) if int(p.forester_patrol_id) == int(unit_id)), None)
                        if patrol:
                            from simulation.agent_state import AGENT_STATE
                            if patrol._state == AGENT_STATE.EXECUTING:
                                skipped_by_state += 1
                                continue
                except Exception as e:
                    logger.debug(f"Error checking agent state for {unit_type} {unit_id}: {e}")
            

            if unit_key in self._travelling_units:
                if not forest_map:
                    skipped += 1
                    continue
            
            filtered.append(action)
        
        if skipped > 0:
            logger.debug(f"Filtered out {skipped} recommendations for units already travelling (fallback)")
        if skipped_by_state > 0:
            logger.debug(f"Filtered out {skipped_by_state} recommendations for units currently EXECUTING")
        
        return filtered
    
    def _update_travelling_units(self, recommendations: List[RecommendedAction]):
        """Update tracking of which units are travelling"""
        new_travelling_keys = {(a['unitType'], a['unitId']) for a in recommendations}
        self._travelling_units.update(new_travelling_keys)
    
    def _update_unit_travelling_status(self, unit_state: Dict, unit_type: str):
        """Update tracking of travelling units based on state updates"""
        unit_id = unit_state.get('fireBrigadeId') or unit_state.get('foresterPatrolId') or unit_state.get('id')
        if unit_id is None:
            return
        
        state = unit_state.get('state', '')
        try:
            unit_id_int = int(unit_id) if isinstance(unit_id, (int, str)) and str(unit_id).isdigit() else str(unit_id)
        except (ValueError, TypeError):
            unit_id_int = str(unit_id)
        
        unit_key = (unit_type, unit_id_int)
        
        # Remove from travelling if unit is now AVAILABLE or IDLE
        # This is critical - units that finished extinguishing should be available for new recommendations
        if state in ['AVAILABLE', 'IDLE']:
            if unit_key in self._travelling_units:
                logger.debug(f"Removing {unit_type} {unit_id} from travelling_units (now {state})")
            self._travelling_units.discard(unit_key)
        # Add to travelling if unit is TRAVELLING or EXTINGUISHING/PATROLLING
        elif state in ['TRAVELLING', 'EXTINGUISHING', 'PATROLLING', 'EXECUTING']:
            self._travelling_units.add(unit_key)
            
    def _recommendations_are_similar(self, new_actions: List[RecommendedAction]) -> bool:
        """
        Check if new recommendations are similar to last published ones.
        Prevents rapid changes when recommendations are essentially the same.
        """
        if not self._last_published_recommendations:
            return False
        
        # Create sets of (unitId, sectorId) tuples for comparison
        new_set = {(a['unitId'], a['sectorId']) for a in new_actions}
        old_set = {(a['unitId'], a['sectorId']) 
                  for a in self._last_published_recommendations.values()}
        
        # If more than stability_threshold are the same, consider them similar
        if not new_set:
            return True
        
        intersection = new_set & old_set
        similarity = len(intersection) / max(len(new_set), len(old_set))
        
        return similarity >= self._stability_threshold
    
    def _can_make_llm_call(self) -> bool:
        """Check if we can make an LLM API call based on rate limiting."""
        if not self._llm_client:
            return False
        
        current_time = time.time()
        self._llm_call_times = [t for t in self._llm_call_times if current_time - t < 60.0]
        
        if len(self._llm_call_times) >= self._max_llm_calls_per_minute:
            logger.debug(f"[LLM-RATE] Rate limit reached: {len(self._llm_call_times)} calls in last minute")
            return False
        
        if self._llm_call_times:
            time_since_last = current_time - self._llm_call_times[-1]
            if time_since_last < self._llm_rate_limit:
                logger.debug(f"[LLM-RATE] Too soon since last call: {time_since_last:.2f}s < {self._llm_rate_limit}s")
                return False
        
        return True
    
    def _record_llm_call(self):
        """Record that an LLM API call was made."""
        self._llm_call_times.append(time.time())
    
    def _generate_llm_recommendations(
        self,
        forest_map,
        min_recommendations: int = 2,
        force_all: bool = False
    ) -> List[tuple]:
        """
        Generate recommendations using LLM when MCTS doesn't produce enough.
        Returns MCTS-format: list of (agent_idx, sector_id) tuples.
        Descriptions are sent to LLM sink separately.
        
        Args:
            forest_map: ForestMap object with agents and sectors
            min_recommendations: Minimum number of recommendations to generate
            
        Returns:
            List of (agent_idx, sector_id) tuples in MCTS format
        """
        if not self._llm_client:
            logger.debug("[LLM-REC] LLM client not available, cannot generate LLM recommendations")
            return []
        
        if not self._can_make_llm_call():
            logger.debug("[LLM-REC] Rate limit reached, skipping LLM recommendation generation")
            return []
        
        try:
            from simulation.fire_brigades.fire_brigade import FireBrigade
            from simulation.forester_patrols.forester_patrol import ForesterPatrol
            from simulation.agent_state import AGENT_STATE
            
            available_brigades = [
                fb for fb in forest_map.fireBrigades
                if isinstance(fb, FireBrigade) and fb._state != AGENT_STATE.EXECUTING
            ]
            
            if not available_brigades:
                logger.debug("[LLM-REC] No available fire brigades for LLM recommendations")
                return []
            
            from simulation.sectors.fire_state import FireState
            
            active_sectors = []
            all_sectors_checked = 0
            sectors_with_fire_level = 0
            sectors_with_active_state = 0
            
            for row in forest_map.sectors:
                for sector in row:
                    all_sectors_checked += 1
                    fire_level = getattr(sector, 'fire_level', 0)
                    fire_state = getattr(sector, 'fire_state', None)
                    
                    has_fire = fire_level > 0 or (fire_state == FireState.ACTIVE)
                    
                    if fire_level > 0:
                        sectors_with_fire_level += 1
                    if fire_state == FireState.ACTIVE:
                        sectors_with_active_state += 1
                    
                    if has_fire:
                        active_sectors.append({
                            "sector_id": sector.sector_id,
                            "fire_level": fire_level,
                            "burn_level": getattr(sector, 'burn_level', 0),
                            "fire_state": str(fire_state) if fire_state else "None",
                            "location": {
                                "latitude": sector.location.latitude if hasattr(sector, 'location') else 0,
                                "longitude": sector.location.longitude if hasattr(sector, 'location') else 0
                            }
                        })
            
            logger.debug(f"[LLM-REC] Checked {all_sectors_checked} sectors: {sectors_with_fire_level} with fire_level>0, {sectors_with_active_state} with ACTIVE state, {len(active_sectors)} total active")
            
            if not active_sectors:
                logger.info(f"[LLM-REC] No active fires found - no recommendations needed (all sectors are safe). Checked {all_sectors_checked} sectors, {sectors_with_fire_level} had fire_level>0, {sectors_with_active_state} had ACTIVE state")
                return []
            
            active_sectors.sort(key=lambda s: s['fire_level'], reverse=True)
            
            peer_actions = []
            if self._agent_communication:
                peer_announcements = self._agent_communication.get_recent_announcements(max_count=20)
                peer_actions = [
                    {
                        "agent_id": ann.get("agent_id"),
                        "action": ann.get("action"),
                        "target_sector_id": ann.get("target_sector_id"),
                        "reasoning": ann.get("reasoning", "")
                    }
                    for ann in peer_announcements
                ]
            
            fire_brigade_list = forest_map.fireBrigades
            forester_patrol_list = getattr(forest_map, "foresterPatrols", [])
            unit_id_to_agent_idx = {}
            for idx, brigade in enumerate(fire_brigade_list):
                try:
                    unit_id = int(brigade.fire_brigade_id)
                    unit_id_to_agent_idx[unit_id] = idx
                except (ValueError, TypeError):
                    continue
            for idx, patrol in enumerate(forester_patrol_list):
                try:
                    unit_id = int(patrol.forester_patrol_id)
                    unit_id_to_agent_idx[unit_id] = len(fire_brigade_list) + idx
                except (ValueError, TypeError):
                    continue
            
            llm_recommendations_mcts = []  # MCTS format: [(agent_idx, sector_id), ...]
            llm_descriptions = []  # Store descriptions for LLM sink
            used_sectors = set()
            used_brigades = set()
            
            if force_all:
                max_llm_calls = len(available_brigades)
                logger.debug(f"[LLM-REC] LLM-ONLY mode: Planning for all {max_llm_calls} available brigades")
            else:
                max_llm_calls = min(5, min_recommendations * 2)
            
            for brigade in available_brigades[:max_llm_calls]:
                if len(llm_recommendations_mcts) >= min_recommendations:
                    break
                
                try:
                    unit_id = int(brigade.fire_brigade_id)
                    if unit_id in used_brigades:
                        continue
                    
                    agent_idx = unit_id_to_agent_idx.get(unit_id)
                    if agent_idx is None:
                        logger.debug(f"[LLM-REC] Could not find agent_idx for unitId {unit_id}, skipping")
                        continue
                    
                    available_for_brigade = [
                        s for s in active_sectors
                        if s['sector_id'] not in used_sectors
                    ]
                    
                    if not available_for_brigade:
                        available_for_brigade = active_sectors[:3]  # Top 3 sectors
                    
                    for sector in available_for_brigade:
                        if hasattr(brigade, 'location') and hasattr(brigade.location, 'latitude'):
                            # Simple distance calculation
                            sector['distance_from_agent'] = 0.1  # Placeholder
                    
                    current_state = {
                        "agent_id": str(unit_id),
                        "state": "AVAILABLE",
                        "location": {
                            "latitude": brigade.location.latitude if hasattr(brigade, 'location') else 0,
                            "longitude": brigade.location.longitude if hasattr(brigade, 'location') else 0
                        },
                        "base_location": {
                            "latitude": brigade.base_location.latitude if hasattr(brigade, 'base_location') else 0,
                            "longitude": brigade.base_location.longitude if hasattr(brigade, 'base_location') else 0
                        }
                    }
                    
                    if not self._can_make_llm_call():
                        logger.debug(f"[LLM-REC] Rate limit reached, skipping LLM call for brigade {unit_id}")
                        if available_for_brigade:
                            target_sector_id = available_for_brigade[0]['sector_id']
                            llm_recommendations_mcts.append((agent_idx, target_sector_id))
                            if unit_id is not None and target_sector_id is not None:
                                llm_descriptions.append({
                                    "unitId": int(unit_id),
                                    "sectorId": int(target_sector_id),
                                    "unitType": "fireBrigade",
                                    "description": f"Extinguish sector {target_sector_id} (fallback - rate limited)",
                                    "reasoning": "Rate limited - using fallback assignment"
                                })
                            used_sectors.add(target_sector_id)
                            used_brigades.add(unit_id)
                        continue
                    
                    # Use LLM to make ecision
                    logger.debug(f"[LLM-REC] Asking LLM for recommendation for brigade {unit_id}")
                    self._record_llm_call()  # Record before making the call
                    decision = self._llm_client.make_decision(
                        agent_id=str(unit_id),
                        current_state=current_state,
                        available_sectors=available_for_brigade[:5],  # Top 5 sectors
                        peer_actions=peer_actions
                    )
                    
                    target_sector_id = decision.get('target_sector_id')
                    decision_type = decision.get('decision', '').lower()
                    
                    if not target_sector_id:
                        if decision_type in ('move_to', 'extinguish') and available_for_brigade:
                            target_sector_id = available_for_brigade[0]['sector_id']
                        elif decision_type == 'stay_idle':
                            if available_for_brigade:
                                target_sector_id = available_for_brigade[0]['sector_id']
                                logger.debug(f"[LLM-REC] LLM suggested stay_idle, but forcing assignment to sector {target_sector_id}")
                    
                    if not target_sector_id and available_for_brigade:
                        target_sector_id = available_for_brigade[0]['sector_id']
                    
                    target_sector = next((s for s in active_sectors if s['sector_id'] == target_sector_id), None)
                    if not target_sector:
                        if available_for_brigade:
                            target_sector = available_for_brigade[0]
                            target_sector_id = target_sector['sector_id']
                        else:
                            logger.debug(f"[LLM-REC] No valid sectors available for brigade {unit_id}")
                            continue
                    
                    llm_recommendations_mcts.append((agent_idx, target_sector_id))
                    
                    if unit_id is not None and target_sector_id is not None:
                        reasoning = decision.get('reasoning') or 'LLM-generated recommendation'
                        if not isinstance(reasoning, str):
                            reasoning = str(reasoning) if reasoning is not None else 'LLM-generated recommendation'
                        
                        llm_descriptions.append({
                            "unitId": int(unit_id),
                            "sectorId": int(target_sector_id),
                            "unitType": "fireBrigade",
                            "description": f"Extinguish sector {target_sector_id} (LLM-driven)",
                            "reasoning": reasoning
                        })
                    
                    used_sectors.add(target_sector_id)
                    used_brigades.add(unit_id)
                    
                    logger.debug(f"[LLM-REC] Generated LLM recommendation: Brigade {unit_id} (idx={agent_idx}) -> Sector {target_sector_id}")
                    
                except Exception as e:
                    logger.error(f"[LLM-REC] Error generating LLM recommendation for brigade {brigade.fire_brigade_id}: {e}", exc_info=True)
                    continue
            
            logger.debug(f"[LLM-REC] Generated {len(llm_recommendations_mcts)} LLM-driven recommendations in MCTS format")
            
            if llm_descriptions:
                try:
                    valid_descriptions = []
                    for desc in llm_descriptions:
                        if (desc.get("unitId") is not None and 
                            desc.get("sectorId") is not None and 
                            desc.get("unitType") is not None and
                            desc.get("description") is not None):
                            valid_desc = {
                                "unitId": int(desc["unitId"]),
                                "sectorId": int(desc["sectorId"]),
                                "unitType": str(desc["unitType"]),
                                "description": str(desc.get("description", "")),
                                "reasoning": str(desc.get("reasoning", "")) if desc.get("reasoning") else ""
                            }
                            valid_descriptions.append(valid_desc)
                        else:
                            logger.warning(f"[LLM-REC] Skipping invalid description: {desc}")
                    
                    if valid_descriptions:
                        desc_parts = []
                        for desc in valid_descriptions:
                            unit_type = desc.get("unitType", "fireBrigade")
                            unit_id = desc.get("unitId", "?")
                            sector_id = desc.get("sectorId", "?")
                            action_desc = desc.get("description", "")
                            reasoning = desc.get("reasoning", "")
                            
                            unit_prefix = "FB" if unit_type == "fireBrigade" else "FP"
                            desc_text = f"{unit_prefix}_{unit_id} -> Sector {sector_id}"
                            if action_desc:
                                desc_text += f": {action_desc}"
                            if reasoning and reasoning != action_desc:
                                desc_text += f" ({reasoning[:50]})"
                            desc_parts.append(desc_text)
                        
                        human_readable_desc = f"{len(valid_descriptions)} recommendations: " + "; ".join(desc_parts)
                        
                        description_message = {
                            "timestamp": datetime.now().isoformat(),
                            "type": "LLM_Recommendation_Descriptions",
                            "agentId": "Strategic_Coordinator",  # Coordinator, not a specific agent
                            "description": human_readable_desc,  # Human-readable description for display
                            "content": json.dumps({
                                "recommendations": valid_descriptions,
                                "source": "Strategic_Coordinator"
                            }),
                            "source": "Strategic_Coordinator"
                        }
                        self.rabbitmq.publish_message(description_message, routing_key='support.llm.responses')
                        logger.debug(f"[LLM-REC] Published {len(valid_descriptions)} recommendation descriptions to LLM sink: {human_readable_desc[:100]}")
                    else:
                        logger.warning("[LLM-REC] No valid descriptions to publish after filtering")
                except Exception as e:
                    logger.error(f"[LLM-REC] Failed to publish descriptions to LLM sink: {e}", exc_info=True)
            
            return llm_recommendations_mcts
            
        except Exception as e:
            logger.error(f"[LLM-REC] Error in _generate_llm_recommendations: {e}", exc_info=True)
            return []
    
    def _coordinate_with_agents(
        self,
        recommended_actions: List[RecommendedAction],
        forest_map
    ) -> List[RecommendedAction]:
        """
        Coordinate recommendations with agent communications.
        Uses LLM to analyze peer actions and adjust recommendations.
        
        Args:
            recommended_actions: List of recommended actions from MCTS
            forest_map: ForestMap object with agents
            
        Returns:
            Coordinated list of recommendations
        """
        if not self._agent_communication or not self._llm_client:
            return recommended_actions
        
        try:
            peer_announcements = self._agent_communication.get_recent_announcements(max_count=50)
            
            if not peer_announcements:
                logger.debug("No peer announcements to coordinate with")
                return recommended_actions
            
            coordinated_actions = []
            
            for action in recommended_actions:
                unit_id = action['unitId']
                sector_id = action['sectorId']
                unit_type = action['unitType']
                
                peer_actions_for_sector = self._agent_communication.get_peer_actions_for_sector(
                    sector_id=sector_id,
                    exclude_agent_id=str(unit_id)
                )
                
                if len(peer_actions_for_sector) >= 2:
                    logger.debug(f"Sector {sector_id} has {len(peer_actions_for_sector)} peers, "
                               f"analyzing with LLM for unit {unit_id}")
                    
                    if not self._can_make_llm_call():
                        logger.debug(f"[LLM-COORD] Rate limit reached, skipping coordination for unit {unit_id}")
                        coordinated_actions.append(action)
                        continue
                    
                    self._record_llm_call()  # Record before making the call
                    analysis = self._llm_client.analyze_peer_actions(
                        agent_id=str(unit_id),
                        my_state={
                            "unit_id": unit_id,
                            "unit_type": unit_type,
                            "recommended_sector_id": sector_id
                        },
                        peer_actions=[
                            {
                                "agent_id": ann.get("agent_id"),
                                "action": ann.get("action"),
                                "target_sector_id": ann.get("target_sector_id"),
                                "reasoning": ann.get("reasoning")
                            }
                            for ann in peer_actions_for_sector
                        ]
                    )
                    
                    adjustment = analysis.get("adjustment", "none")
                    
                    if adjustment == "change_target" and "new_target_sector_id" in analysis:
                        new_sector_id = analysis["new_target_sector_id"]
                        action_copy = action.copy()
                        action_copy["sectorId"] = new_sector_id
                        action_copy["description"] = f"{action['description'].split()[0]} sector {new_sector_id} (adjusted based on peer coordination)"
                        action_copy["reasoning"] = analysis.get("reasoning", "Peer coordination")
                        coordinated_actions.append(action_copy)
                        logger.info(f"[SUPPORT-COORD] Unit {unit_id} redirected from sector {sector_id} "
                                  f"to {new_sector_id} based on LLM coordination")
                    elif adjustment == "abort_current":
                        logger.info(f"[SUPPORT-COORD] Unit {unit_id} recommendation for sector {sector_id} "
                                  f"skipped based on peer coordination")
                        continue
                    else:
                        coordinated_actions.append(action)
                else:
                    coordinated_actions.append(action)
            
            if len(coordinated_actions) != len(recommended_actions):
                logger.info(f"[SUPPORT-COORD] Coordinated {len(recommended_actions)} actions to {len(coordinated_actions)} "
                          f"based on agent communications")
            
            return coordinated_actions
            
        except Exception as e:
            logger.error(f"Error coordinating with agents: {e}", exc_info=True)
            return recommended_actions
    
    # HTTP API methods
    def get_state_snapshot(self) -> Dict:
        """Get current state snapshot for HTTP API"""
        sectors, fire_brigades, forester_patrols = self.state_manager.get_state_copy()
        return {
            "sectors": sectors,
            "fireBrigades": fire_brigades,
            "foresterPatrols": forester_patrols,
            "lastUpdateTime": self.state_manager.last_update_time
        }
    
    def update_state(self, payload: Dict) -> None:
        """Update state from HTTP POST"""
        if not payload:
            return
        
        config = payload.get('config')
        if config:
            self.state_manager.set_config(config)
        
        sectors = payload.get('sectors', {})
        fire_brigades = payload.get('fireBrigades', {})
        forester_patrols = payload.get('foresterPatrols', {})
        
        for sector in sectors.values():
            self.state_manager.update_sector_state(sector)
        for brigade in fire_brigades.values():
            self.state_manager.update_fire_brigade_state(brigade)
        for patrol in forester_patrols.values():
            self.state_manager.update_forester_patrol_state(patrol)
    
    def analyze_now(self) -> Optional[Dict]:
        """Trigger immediate analysis and return recommendations"""
        self._generate_recommendations()
        with self._last_recommendations_lock:
            return dict(self._last_recommendations) if self._last_recommendations else None
    
    def get_last_recommendations(self) -> Optional[Dict]:
        """Get last generated recommendations"""
        with self._last_recommendations_lock:
            return dict(self._last_recommendations) if self._last_recommendations else None
    
    def _test_llm_initialization(self):
        """Test LLM initialization with a simple call"""
        try:
            logger.info("=" * 80)
            logger.debug("[LLM-TEST] Running initialization test...")
            logger.info("=" * 80)
            
            # Simple test decision
            test_state = {
                "agent_id": "init_test",
                "state": "AVAILABLE",
                "location": {"latitude": 0.0, "longitude": 0.0},
                "base_location": {"latitude": 0.0, "longitude": 0.0},
                "destination": {"latitude": 0.0, "longitude": 0.0}
            }
            
            test_sectors = [{
                "sector_id": 1,
                "fire_level": 50.0,
                "burn_level": 0.0,
                "location": {"latitude": 0.1, "longitude": 0.1},
                "distance_from_agent": 0.14,
                "number_of_brigades": 0
            }]
            
            logger.debug("[LLM-TEST] Making test LLM call...")
            decision = self._llm_client.make_decision(
                agent_id="init_test",
                current_state=test_state,
                available_sectors=test_sectors,
                peer_actions=[]
            )
            
            logger.debug(f"[LLM-TEST] Test call successful!")
            logger.debug(f"[LLM-TEST] Decision: {decision.get('decision', 'N/A')}")
            logger.debug(f"[LLM-TEST] Reasoning: {decision.get('reasoning', 'N/A')[:100]}")
            logger.debug(f"[LLM-TEST] Mode: REAL API")
            logger.info("=" * 80)
            
            # Test agent communication if available
            if self._agent_communication:
                logger.debug("[LLM-TEST] Testing agent communication...")
                self._agent_communication.announce_action(
                    agent_id="init_test",
                    action="initialization_test",
                    target_sector_id=1,
                    reasoning="LLM initialization test announcement"
                )
                logger.debug("[LLM-TEST] Agent communication test successful!")
                logger.info("=" * 80)
            
        except Exception as e:
            logger.error(f"[LLM-TEST]   Initialization test failed: {e}", exc_info=True)
            logger.debug("[LLM-TEST] LLM may not work correctly - check configuration")
            logger.info("=" * 80)
    def _handle_llm_proposition(self, message: Dict):
        """Handle natural language propositions from agents and respond via chat"""
        if not self._llm_client: 
            return
        
        agent_id = message.get("agentId", "Unknown")
        proposition = message.get("description", "")
        
        try:
            if hasattr(self._llm_client, "evaluate_proposition"):
                context = None
                if self.state_manager:
                    try:
                        context = {
                            "active_fires": len([s for s in self.state_manager.get_all_sectors() if s.get('state', {}).get('fireLevel', 0) > 0]),
                            "available_brigades": len([b for b in self.state_manager.get_all_fire_brigades() if b.get('state') == 'available'])
                        }
                    except Exception as e:
                        logger.debug(f"Could not get context for proposition evaluation: {e}")
                
                response_text = self._llm_client.evaluate_proposition(agent_id, proposition, context)
            else:
                # Fallback to generic complete method
                system_prompt = """You are the Strategic Fire Coordinator overseeing fire brigades.
IMPORTANT: 
- Always explain your decision reasoning
- Reference specific sectors when responding
- Provide tactical guidance, not just approval/denial
- Be supportive of good proposals, challenging of weak ones
- Keep response under 25 words but be detailed"""
                
                user_prompt = f"""Agent {agent_id} proposes: "{proposition}"
                
Evaluate this proposal:
1. Is it strategically sound?
2. What are the implications?
3. Should you approve, modify, or deny?

Respond with a detailed tactical decision that explains reasoning."""
                
                response_text = self._llm_client.complete(user_prompt, system_prompt)
            
            # Send response back to support.llm.responses (which agents listen to)
            response_msg = {
                "timestamp": datetime.now().isoformat(),
                "type": "CoordinatorResponse",
                "description": response_text,
                "content": json.dumps({
                    "proposition": response_text,
                    "reasoning": "Strategic decision based on agent request",
                    "affectedAgents": [agent_id]
                }),
                "source": "Strategic_Coordinator",
                "agentId": agent_id
            }
            
            # Publish response on both channels for compatibility
            self.rabbitmq.publish_message(response_msg, routing_key="support.llm.responses")
            self.rabbitmq.publish_message(response_msg, routing_key="support.llm.propositions.responses")
            
        except Exception as e:
            logger.error(f"Error handling LLM proposition: {e}")

    def _handle_proposition_response(self, message: Dict):
        """Handle responses to agent propositions (logging/tracking)"""
        try:
            agent_id = message.get("content", {}).get("affectedAgents", ["Unknown"])[0]
            proposition_text = message.get("content", {}).get("proposition", "No response")
            logger.debug(f"[LLM-PROP-RESPONSE] {agent_id} received coordinator response: {proposition_text}")
        except Exception as e:
            logger.error(f"Error handling proposition response: {e}")
    
    def _generate_llm_predictions_from_announcements(self):
        """
        Generate predictions from agent announcements and sector states.
        Only runs in LLM mode. Publishes predictions in two formats:
        1. Human-readable for LLM chat (support.llm.responses)
        2. Contracts format for backend/frontend (support.recommendations)
        """
        if not self._llm_config or not self._llm_config.use_llm_coordination:
            return
        
        if not self._llm_client or not self._agent_communication:
            return
        
        # Check rate limit
        if not self._can_make_llm_call():
            logger.debug("[LLM-PRED] Rate limit reached, skipping prediction generation")
            return
        
        try:
            with self._chat_lock:
                announcements = list(self._pending_chat_requests[-20:])  # Last 20 announcements
                if not announcements:
                    announcements = self._agent_communication.get_recent_announcements(max_count=50) if self._agent_communication else []
            
            if not announcements:
                logger.debug("[LLM-PRED] No agent announcements available for prediction")
                return
            
            logger.info(f"[LLM-PRED] Generating predictions from {len(announcements)} agent announcements")
            
            sectors, fire_brigades, forester_patrols = self.state_manager.get_state_copy()
            active_fires = [s for s in sectors.values() if s.get('state', {}).get('fireLevel', 0) > 0]
            
            announcement_summary = []
            for ann in announcements:
                agent_id = ann.get('agent_id', 'Unknown')
                natural_lang = ann.get('natural_language') or ann.get('reasoning', '') or ann.get('action', '')
                sector_id = ann.get('target_sector_id') or ann.get('sector')
                status = ann.get('status', 'UNKNOWN')
                announcement_summary.append({
                    "agent": agent_id,
                    "message": natural_lang[:100] if natural_lang else f"Status: {status}",
                    "sector": sector_id,
                    "status": status
                })
            
            system_prompt = """You are a Strategic Fire Coordinator analyzing agent status updates and sector conditions.
Your task is to:
1. Analyze agent announcements and current fire situation
2. Predict which sectors need immediate attention
3. Recommend actions for available agents
4. Provide both a human-readable summary and structured recommendations

Return JSON with:
- "human_readable": A natural language summary of the situation and predictions
- "recommendations": List of recommended actions with unitId, sectorId, unitType, description, priority, reasoning"""
            
            user_prompt = f"""Analyze the current firefighting situation:

AGENT STATUS UPDATES (last 20):
{json.dumps(announcement_summary, indent=2)}

ACTIVE FIRES:
- {len(active_fires)} sectors with active fires
- Top fire levels: {sorted([s.get('state', {}).get('fireLevel', 0) for s in active_fires], reverse=True)[:5]}

AVAILABLE UNITS:
- Fire Brigades: {len([b for b in fire_brigades.values() if b.get('state') == 'AVAILABLE'])}
- Forester Patrols: {len([p for p in forester_patrols.values() if p.get('state') == 'AVAILABLE'])}

Generate predictions and recommendations. Return JSON with human_readable summary and recommendations array."""
            
            self._record_llm_call()
            response_text = self._llm_client.complete(user_prompt, system_prompt)
            
            if not response_text:
                logger.warning("[LLM-PRED] Empty response from LLM")
                return
            
            try:
                if response_text.strip().startswith("{"):
                    prediction_data = json.loads(response_text.strip())
                elif "{" in response_text and "}" in response_text:
                    start = response_text.find("{")
                    end = response_text.rfind("}") + 1
                    prediction_data = json.loads(response_text[start:end])
                else:
                    prediction_data = {
                        "human_readable": response_text[:500],
                        "recommendations": []
                    }
                
                human_readable = prediction_data.get("human_readable", response_text[:500])
                chat_message = {
                    "timestamp": datetime.now().isoformat(),
                    "type": "LLM_Prediction",
                    "agentId": "Strategic_Coordinator",
                    "content": json.dumps({
                        "prediction": human_readable,
                        "source": "Strategic_Coordinator",
                        "based_on_announcements": len(announcements)
                    }),
                    "source": "Strategic_Coordinator"
                }
                self.rabbitmq.publish_message(chat_message, routing_key='support.llm.responses')
                logger.info(f"[LLM-PRED] Published human-readable prediction to LLM chat")
                
                llm_recommendations = prediction_data.get("recommendations", [])
                if llm_recommendations:
                    recommended_actions = []
                    for rec in llm_recommendations:
                        if isinstance(rec, dict):
                            unit_id = rec.get("unitId")
                            sector_id = rec.get("sectorId")
                            
                            try:
                                if isinstance(unit_id, str):
                                    unit_id = int(unit_id)
                                if isinstance(sector_id, str):
                                    sector_id = int(sector_id)
                            except (ValueError, TypeError):
                                logger.warning(f"[LLM-PRED] Invalid unitId or sectorId in recommendation: unitId={rec.get('unitId')}, sectorId={rec.get('sectorId')}")
                                continue
                            
                            action = {
                                "unitId": unit_id,
                                "sectorId": sector_id,
                                "unitType": rec.get("unitType", "fireBrigade"),
                                "description": rec.get("description", "LLM-generated recommendation"),
                                "priority": rec.get("priority", 5),
                                "reasoning": rec.get("reasoning", "Based on agent announcements and sector analysis")
                            }
                            
                            if action.get("unitId") is not None and action.get("sectorId") is not None:
                                if action["unitType"] not in ["fireBrigade", "foresterPatrol"]:
                                    logger.warning(f"[LLM-PRED] Invalid unitType '{action['unitType']}', defaulting to 'fireBrigade'")
                                    action["unitType"] = "fireBrigade"
                                recommended_actions.append(action)
                            else:
                                logger.warning(f"[LLM-PRED] Skipping recommendation with missing unitId or sectorId: {rec}")
                    
                    if recommended_actions:
                        recommendation_message: RecommendationMessage = {
                            "timestamp": time.time(),
                            "recommendedActions": recommended_actions,
                            "priority": "HIGH"
                        }
                        
                        logger.debug(f"[LLM-PRED] Recommendation message: {json.dumps(recommendation_message, indent=2)}")
                        
                        success = self.rabbitmq.publish_recommendation(recommendation_message)
                        if success:
                            logger.info(f"[LLM-PRED] Published {len(recommended_actions)} LLM-generated recommendations in contracts format")
                        else:
                            logger.error("[LLM-PRED] Failed to publish recommendations")
                    else:
                        logger.warning("[LLM-PRED] No valid recommendations after processing LLM response")
                
            except json.JSONDecodeError as e:
                logger.error(f"[LLM-PRED] Failed to parse LLM response as JSON: {e}")
                logger.debug(f"[LLM-PRED] Response was: {response_text[:200]}")

                chat_message = {
                    "timestamp": datetime.now().isoformat(),
                    "type": "LLM_Prediction",
                    "agentId": "Strategic_Coordinator",
                    "content": json.dumps({
                        "prediction": response_text[:500],
                        "source": "Strategic_Coordinator"
                    }),
                    "source": "Strategic_Coordinator"
                }
                self.rabbitmq.publish_message(chat_message, routing_key='support.llm.responses')
                
        except Exception as e:
            logger.error(f"[LLM-PRED] Error generating predictions from announcements: {e}", exc_info=True)
        finally:
            self._last_chat_response_time = time.time()

    '''
        If you did not notice most of it was LLM generated code.
        Feel free to refactor it to your liking.
        Most of it should be removed to simplify project... 
    '''
    
    def _should_use_llm_mode(self, forest_map) -> bool:
        """
        Autonomous mode switching: decides whether to use LLM or MCTS based on situation.
        
        Returns True if LLM mode should be used, False for MCTS mode.
        """
        from simulation.agent_state import AGENT_STATE
        
        if not self._llm_config.use_llm_coordination:
            logger.info("[MODE] LLM coordination disabled (ENABLE_LLM_COORDINATION=false), using MCTS")
            return False
        
        if self._llm_config.recommendation_mode == "llm":
            if not self._llm_config.use_llm_coordination:
                logger.info("[MODE] RECOMMENDATION_MODE=llm but ENABLE_LLM_COORDINATION=false, using MCTS")
                return False
            logger.info("[MODE] Using LLM mode (RECOMMENDATION_MODE=llm and ENABLE_LLM_COORDINATION=true)")
            return True
        if self._llm_config.recommendation_mode == "heuristic":
            logger.info("[MODE] Using MCTS mode (RECOMMENDATION_MODE=heuristic)")
            return False
        
        if self._llm_config.recommendation_mode == "auto" or self._llm_config.recommendation_mode == "hybrid":
            if forest_map is None:
                logger.debug("[MODE] Auto/hybrid mode but no forest_map, using MCTS")
                return False

            if not self._llm_client or not self._llm_client.api_key:
                logger.debug("[AUTO-MODE] LLM not available, using MCTS")
                return False
            
            if not self._can_make_llm_call():
                logger.debug("[AUTO-MODE] LLM rate limited, using MCTS")
                return False
            
            all_sectors = [s for row in forest_map.sectors for s in row]
            sectors_with_fire = [s for s in all_sectors if s.fire_level > 0]
            active_fires_count = len(sectors_with_fire)
            total_fire_level = sum(s.fire_level for s in sectors_with_fire)
            avg_fire_level = total_fire_level / max(active_fires_count, 1)
            available_agents = len([a for a in forest_map.fireBrigades if a._state == AGENT_STATE.AVAILABLE])
            total_agents = len(forest_map.fireBrigades)
            
            # Decision criteria:
            # - Use LLM for complex situations (many fires, high fire levels, many agents)
            # - Use MCTS for simple situations (few fires, low fire levels, few agents)
            complexity_score = (
                (active_fires_count / max(len(all_sectors), 1)) * 0.4 +  # Fire spread
                (avg_fire_level / 100.0) * 0.3 +  # Fire intensity
                (total_agents / max(available_agents + 1, 1)) * 0.3  # Agent utilization
            )
            
            use_llm = complexity_score > 0.3  # Threshold for LLM mode
            
            if use_llm:
                logger.info(f"[AUTO-MODE] Using LLM (complexity={complexity_score:.2f}, fires={active_fires_count}, avg_level={avg_fire_level:.1f})")
            else:
                logger.info(f"[AUTO-MODE] Using MCTS (complexity={complexity_score:.2f}, fires={active_fires_count}, avg_level={avg_fire_level:.1f})")
            
            return use_llm
        
        return self._llm_config.recommendation_mode == "llm"
