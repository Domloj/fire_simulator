import asyncio
import threading
import time
import logging
import random
from typing import Any, Dict, Optional
import os

from src.settings.communucation_settings import CommunicationSettings, SimulatorCommunicationSettings, get_simulator_settings
from src.settings.simulation_settings import SimulationSettings, get_simulation_settings
from src.engine.base import SimulationEngine
from src.engine.simple_simulation_engine import SimpleSimulationEngine
from src.engine.models.sensors.sensor_type import SensorType
from src.messaging.topics import (
    TopicRegistry, 
    get_topic_for_sensor, 
    get_all_topics,
    SimulationTopics,
    ControlTopics
)
from src.rabbitmq.message_store import MessageStore
from src.rabbitmq.pika_client import PikaClient
from src.rabbitmq import producer, consumer, connection_manager
from src.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)

class EngineRunner:
    def __init__(
        self, 
        engine: SimulationEngine                = None, 
        settings: SimulatorCommunicationSettings = None, 
        simulation_settings: SimulationSettings = None,
        store: MessageStore                     = None,
        client: PikaClient                      = None
    ):
        self.engine = engine if engine else SimpleSimulationEngine()
        self.settings = settings if settings else get_simulator_settings()
        self.simulation_settings = simulation_settings if simulation_settings else get_simulation_settings()
        self.store = store if store else MessageStore()
        self.client = client if client else PikaClient()

        self._stop = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._write_threads = []
        self._read_threads = []
        self._tick_interval = self.simulation_settings.tick_interval
        self._base_tick_interval = self.simulation_settings.tick_interval
        self._min_tick_interval = 0.05
        self._max_tick_interval = 2.0
        self._command_consumer = None
        self._original_config = None
        self._last_fire_count = 0

    def set_tick_interval(self, seconds: float) -> None:
        try:
            value = float(seconds)
            if value > 0:
                logger.info("Updating EngineRunner tick interval to %s seconds", value)
                self._tick_interval = value
                self.simulation_settings.tick_interval = value
        except (TypeError, ValueError):
            pass

    async def start(self, config: Dict[str, Any]) -> None:
        import random 

        self._original_config = config.copy() if config else None
        self._simulation_session_id = f"sim_{int(time.time())}_{random.randint(1000, 9999)}"
        self._original_config['simulationSessionId'] = self._simulation_session_id if self._original_config else None
            
        logger.info(f"Starting new simulation session: {self._simulation_session_id}")
        
        await self.engine.load_config(config)
        
        if hasattr(self.engine, 'agents_manager') and self.engine.agents_manager:
            self.engine.agents_manager._message_store = self.store
            
            shared_llm_client = None
            if self.engine.agents_manager._enable_llm_agents:
                try:
                    logger.info("[LLM] Initializing shared LLM client for agents...")
                    logger.info(f"[LLM] ENABLE_LLM_AGENTS={os.getenv('ENABLE_LLM_AGENTS', 'not set')}")
                    shared_llm_client = LLMClient()
                    logger.info(f"[LLM] API Key: {'SET' if shared_llm_client.api_key else 'NOT SET'}")
                except Exception as e:
                    logger.warning("[LLM] Continuing simulation WITHOUT LLM support - agents will use fallback announcements")
                    shared_llm_client = None
                    # Continue without LLM - don't crash simulation
            else:
                logger.info("[LLM] LLM agents disabled (ENABLE_LLM_AGENTS=false or not set)")

            if self.engine.agents_manager._agent_communication is None and self.engine.agents_manager._enable_llm_agents:
                try:
                    logger.info("[LLM] Setting up agent communication...")
                    from src.llm.agent_communication import AgentCommunication
                    comm = AgentCommunication(self.store)
                    self.engine.agents_manager._agent_communication = comm
                    agents_with_llm = 0
                    for agent in self.engine.agents_manager._agents.values():
                        agent.set_communication(comm)
                        if shared_llm_client:
                            agent.set_llm_client(shared_llm_client) # Pass LLM to agent
                            agent._llm_chat_enabled = True
                            agents_with_llm += 1
                    logger.info(f"[LLM] ✓ Late-bound agent communication initialized for {len(self.engine.agents_manager._agents)} agents ({agents_with_llm} with LLM client)")
                except Exception as e:
                    logger.error(f"[LLM] ✗ Failed late-bound communication init: {e}", exc_info=True)
                    logger.warning("[LLM] Continuing simulation WITHOUT agent communication - agents will use fallback announcements")
                    # Continue without agent communication - don't crash simulation
            elif not self.engine.agents_manager._enable_llm_agents:
                logger.info("[LLM] Agent communication skipped (ENABLE_LLM_AGENTS disabled)")
            logger.info("Message store set for agent manager")
        
        await self.engine.start()

        self._setup_queues()
        self._publish_support_config()
        
        if hasattr(self.engine, 'agents_manager') and self.engine.agents_manager:
            from src.engine.agent_manager.command_consumer import CommandConsumer

            self._command_consumer = CommandConsumer(
                message_store    = self.store,
                command_callback = self.engine.agents_manager.process_command,
                forest_map       = self.engine._map
            )
            self._command_consumer.start()

            logger.info("CommandConsumer started")

        logger.info("Waiting for queues to initialize...")
        await asyncio.sleep(1.0)

        self._stop.clear()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True, name="EngineRunnerLoop")
        self._loop_thread.start()
        logger.info("Simulation loop started")

    def _setup_queues(self):
        with self.client.connection_ctx() as (connection, channel):
            if connection and channel:
                try:
                    channel.exchange_declare(
                        exchange      = self.settings.exchange_name,
                        exchange_type = 'topic',
                        durable       = False
                    )
                    
                    all_topics = get_all_topics()
                    for topic in all_topics:
                        queue_name = topic.replace('.', '_')
                        channel.queue_declare(queue=queue_name, durable=False)
                        channel.queue_bind(
                            exchange    = self.settings.exchange_name,
                            queue       = queue_name,
                            routing_key = topic
                        )
                    logger.info(f"Created and bound {len(all_topics)} queues")
                except Exception as e:
                    logger.error(f"Error setting up queues: {e}")

        for topic_value in SimulationTopics.ALL:
            topic_enum = next((t for t in TopicRegistry if t.value == topic_value), None)
            if topic_enum:
                logger.info(f"Starting producer thread for topic: {topic_enum.value} (enum: {topic_enum.name})")
                self._start_producer_thread(topic_enum)
            else:
                logger.warning(f"No TopicRegistry enum found for topic value: {topic_value}")
        
        self._start_producer_thread(TopicRegistry.SUPPORT_AGGREGATED_DATA)

        for topic in [
            TopicRegistry.FORESTER_ACTIONS, 
            TopicRegistry.FIRE_BRIGADE_ACTIONS,
            TopicRegistry.LLM_RESPONSES,
            TopicRegistry.AGENT_ANNOUNCEMENTS
        ]:
            self._start_consumer_thread(topic)

    def _publish_support_config(self) -> None:
        if not self._original_config:
            logger.warning("Support config publish skipped: missing original config")
            return

        try:
            support_topic = TopicRegistry.SUPPORT_AGGREGATED_DATA.value
            self.store.add_message_to_sent(support_topic, self._original_config)
            logger.info("Published configuration to support.data.aggregated")
        except Exception as e:
            logger.error(f"Failed to publish support config: {e}")

    def _start_producer_thread(self, topic):
        thread = threading.Thread(
            target=producer.start_producing_messages,
            kwargs={
                "exchange": self.settings.exchange_name,
                "routing_key": topic.value,
                "store": self.store,
                "username": self.settings.rabbitmq_username,
                "password": self.settings.rabbitmq_password,
                "host": self.settings.rabbitmq_host,
                "port": self.settings.rabbitmq_port,
                "stop_event": self._stop
            },
            daemon=True,
            name=f"Producer-{topic.name}"
        )
        thread.start()
        self._write_threads.append(thread)

    def _start_consumer_thread(self, topic):
        queue_name = topic.value.replace('.', '_')
        thread = threading.Thread(
            target=consumer.consume_messages_from_queue,
            kwargs={
                "queue_name": queue_name,
                "store": self.store,
                "username": self.settings.rabbitmq_username,
                "password": self.settings.rabbitmq_password,
                "host": self.settings.rabbitmq_host,
                "port": self.settings.rabbitmq_port,
                "stop_event": self._stop
            },
            daemon=True,
            name=f"Consumer-{topic.name}"
        )
        thread.start()
        self._read_threads.append(thread)

    def _run_loop(self):
        logger.info("Starting EngineRunner loop execution")
        step_count = 0
        while not self._stop.is_set():
            try:
                step_count += 1
                logger.info(f"Loop iteration {step_count}, calling step... (tick_interval={self._tick_interval}, _stop.is_set()={self._stop.is_set()})")
                self._do_step_and_send()
                logger.info(f"Step {step_count} completed, sleeping for {self._tick_interval}s")
                self._adjust_tick_interval()
                time.sleep(self._tick_interval)
            except Exception as e:
                logger.exception(f"Error in simulation loop: {e}")
                break
        logger.info(f"Simulation loop exited after {step_count} steps")

    def _do_step_and_send(self):
        logger.info("_do_step_and_send: calling engine.step(1)")
        try:
            result = self.engine.step(1)
            logger.info(f"_do_step_and_send: step completed, tick={result.get('tick', 'unknown')}, sectors={len(result.get('sector_states', []))}, agents={len(result.get('agent_states', []))}")
        except Exception as e:
            logger.exception(f"Error in engine.step(1): {e}")
            raise
        
        sector_states = result.get("sector_states", [])
        sector_states_fast = result.get("sector_states_fast", [])
        sensor_messages = result.get("sensor_messages", {})
        agent_states = result.get("agent_states", [])
        events = result.get("events", [])
        
        try:
            self._process_sensor_messages(sensor_messages)
            logger.debug(f"Processed {len(sensor_messages)} sensor message types")
        except Exception as e:
            logger.exception(f"Error in _process_sensor_messages: {e}")
            raise
        
        try:
            self._process_sector_states(sector_states)
            logger.debug(f"Processed {len(sector_states)} sector states")
        except Exception as e:
            logger.exception(f"Error in _process_sector_states: {e}")
            raise
        
        try:
            self._process_sector_states_fast(sector_states_fast)
            logger.debug(f"Processed {len(sector_states_fast)} fast sector states")
        except Exception as e:
            logger.exception(f"Error in _process_sector_states_fast: {e}")
            raise
        
        try:
            self._process_agent_states(agent_states)
            logger.debug(f"Processed {len(agent_states)} agent states")
        except Exception as e:
            logger.exception(f"Error in _process_agent_states: {e}")
            raise
        
        try:
            self._process_events(events)
            logger.debug(f"Processed {len(events)} events")
        except Exception as e:
            logger.exception(f"Error in _process_events: {e}")
            raise
        
        # Throttle support data updates to ~2Hz (every 500ms)
        # This prevents flooding the support service with high-frequency agent updates
        now = time.time()
        if not hasattr(self, '_last_support_update'):
            self._last_support_update = 0
            
        if now - self._last_support_update >= 0.5:
            try:
                self._process_support_aggregated_data(sector_states, agent_states)
                self._last_support_update = now
                logger.debug("Published support aggregated data")
            except Exception as e:
                logger.exception(f"Error in _process_support_aggregated_data: {e}")
                # Don't raise here - support data is not critical for simulation loop

    def _process_sensor_messages(self, sensor_messages):
        for sensor_type_name, payloads in sensor_messages.items():
            try:
                sensor_type = SensorType[sensor_type_name]
                topic = get_topic_for_sensor(sensor_type)
                for payload in payloads:
                    self.store.add_message_to_sent(topic, payload)
            except (KeyError, ValueError):
                pass

    def _process_sector_states(self, sector_states):
        routing_key = TopicRegistry.SECTOR_STATE.value
        session_id = getattr(self, '_simulation_session_id', None)
        for state in sector_states:
            if session_id:
                state['simulationSessionId'] = session_id
            self.store.add_message_to_sent(routing_key, state)

    def _process_sector_states_fast(self, sector_states_fast):
        routing_key = TopicRegistry.SECTOR_STATE_FAST.value
        session_id = getattr(self, '_simulation_session_id', None)
        for state in sector_states_fast:
            if session_id:
                state['simulationSessionId'] = session_id
            self.store.add_message_to_sent(routing_key, state)

    def _process_agent_states(self, agent_states):
        batches = {
            "fireBrigade": [],
            "foresterPatrol": []
        }
        
        session_id = getattr(self, '_simulation_session_id', None)
        
        for agent_state in agent_states:
            if session_id:
                agent_state['simulationSessionId'] = session_id
                
            agent_type = agent_state.get("type")
            
            # Map agent types to batch categories
            if agent_type in ["fire_brigade", "fireBrigade"]:
                batches["fireBrigade"].append(agent_state)
            elif agent_type in ["forester", "foresterPatrol"]:
                batches["foresterPatrol"].append(agent_state)
                
        # Send batches
        if batches["fireBrigade"]:
            self.store.add_message_to_sent(
                TopicRegistry.FIRE_BRIGADE_STATE_BATCH.value, 
                {"batch": batches["fireBrigade"]}
            )
            
        if batches["foresterPatrol"]:
            self.store.add_message_to_sent(
                TopicRegistry.FORESTER_STATE_BATCH.value, 
                {"batch": batches["foresterPatrol"]}
            )

    def _process_events(self, events):
        session_id = getattr(self, '_simulation_session_id', None)
        for event in events:
            if session_id:
                event['simulationSessionId'] = session_id
            self.store.add_message_to_sent(TopicRegistry.EVENTS.value, event)

    def _process_support_aggregated_data(self, sector_states, agent_states):
        """Aggregate and publish data for support service"""
        sectors_dict = {}
        forest_id = self._original_config.get('forestId') if self._original_config else None

        # Prefer explicit sector_states from the engine; if empty, synthesize
        # a full view from the current map so support always sees something.
        sector_state_source = sector_states
        if (not sector_state_source) and hasattr(self.engine, "all_sectors"):
            sector_state_source = []
            try:
                for sector in getattr(self.engine, "all_sectors", []):
                    if hasattr(sector, "make_sector_json"):
                        sector_state_source.append(sector.make_sector_json())
            except Exception:
                # fall back to original (possibly empty) list
                sector_state_source = sector_states

        for sector_state in sector_state_source:
            sector_id = sector_state.get('sectorId')
            if sector_id is not None:
                sector_for_support = {
                    "sectorId": sector_id,
                    "forestId": forest_id,
                    "simulationSessionId": getattr(self, '_simulation_session_id', None),
                    "state": {
                        "fireLevel": sector_state.get('fireLevel', 0.0),
                        "burnLevel": sector_state.get('burnLevel', 0.0),
                        "extinguishLevel": sector_state.get('extinguishLevel', 0.0)
                    }
                }
                sectors_dict[str(sector_id)] = sector_for_support
        
        fire_brigades_list = []
        forester_patrols_list = []
        
        for agent_state in agent_states:
            agent_type = agent_state.get("type", "")
            if agent_type in ["fire_brigade", "fireBrigade"]:
                brigade_for_support = {
                    "fireBrigadeId": agent_state.get('fireBrigadeId') or agent_state.get('id') or agent_state.get('agentId'),
                    "forestId": forest_id,
                    "simulationSessionId": getattr(self, '_simulation_session_id', None),
                    "state": agent_state.get("state", "AVAILABLE"),
                    "location": agent_state.get("location", {})
                }
                if brigade_for_support["fireBrigadeId"] is not None:
                    fire_brigades_list.append(brigade_for_support)
            elif agent_type in ["forester", "foresterPatrol"]:
                patrol_for_support = {
                    "foresterPatrolId": agent_state.get('foresterPatrolId') or agent_state.get('id') or agent_state.get('agentId'),
                    "forestId": forest_id,
                    "simulationSessionId": getattr(self, '_simulation_session_id', None),
                    "state": agent_state.get("state", "AVAILABLE"),
                    "location": agent_state.get("location", {})
                }
                if patrol_for_support["foresterPatrolId"] is not None:
                    forester_patrols_list.append(patrol_for_support)
        
        fire_brigades_dict = {}
        for brigade in fire_brigades_list:
            brigade_id = str(brigade.get('fireBrigadeId', ''))
            if brigade_id:
                fire_brigades_dict[brigade_id] = brigade
        
        forester_patrols_dict = {}
        for patrol in forester_patrols_list:
            patrol_id = str(patrol.get('foresterPatrolId', ''))
            if patrol_id:
                forester_patrols_dict[patrol_id] = patrol
        
        aggregated_message = {
            "timestamp": time.time(),
            "forestId": forest_id,
            "simulationSessionId": getattr(self, '_simulation_session_id', None),
            "sectors": sectors_dict,
            "fireBrigades": fire_brigades_dict if fire_brigades_dict else fire_brigades_list,
            "foresterPatrols": forester_patrols_dict if forester_patrols_dict else forester_patrols_list
        }
        
        support_topic = TopicRegistry.SUPPORT_AGGREGATED_DATA.value
        self.store.add_message_to_sent(support_topic, aggregated_message)
        
        logger.debug(f"Published to support.data.aggregated: sectors={len(sectors_dict)}, "
                    f"fireBrigades={len(fire_brigades_dict) or len(fire_brigades_list)}, "
                    f"foresterPatrols={len(forester_patrols_dict) or len(forester_patrols_list)}")

    def _adjust_tick_interval(self):
        if not hasattr(self.engine, 'sectors_on_fire'):
            return
        
        current_fire_count = len(self.engine.sectors_on_fire)
        if abs(current_fire_count - self._last_fire_count) > 2:
            if current_fire_count > 0:
                fire_factor = min(current_fire_count / 20.0, 0.6)
                new_interval = self._base_tick_interval * (1.0 - fire_factor)
                new_interval = max(new_interval, self._min_tick_interval)
            else:
                new_interval = min(self._base_tick_interval * 1.5, self._max_tick_interval)
            
            self._tick_interval = new_interval
        self._last_fire_count = current_fire_count

    async def stop(self):
        logger.info("Stopping EngineRunner...")
        self._stop.set()
        
        # Stop command consumer
        if self._command_consumer:
            try:
                self._command_consumer.stop()
            except Exception as e:
                logger.error(f"Error stopping command consumer: {e}", exc_info=True)
        
        # Wait for main loop thread
        if self._loop_thread and self._loop_thread.is_alive():
            logger.debug("Waiting for main loop thread to stop...")
            self._loop_thread.join(timeout=2.0)
            if self._loop_thread.is_alive():
                logger.warning("Main loop thread did not stop within timeout")

        # Wait for producer and consumer threads
        all_threads = self._write_threads + self._read_threads
        if all_threads:
            logger.debug(f"Waiting for {len(all_threads)} producer/consumer threads to stop...")
            for t in all_threads:
                if t.is_alive():
                    try:
                        t.join(timeout=1.0)
                        if t.is_alive():
                            logger.warning(f"Thread {t.name} did not stop within timeout")
                    except Exception as e:
                        logger.error(f"Error waiting for thread {t.name}: {e}", exc_info=True)
        
        # Stop engine
        try:
            await self.engine.stop()
        except Exception as e:
            logger.error(f"Error stopping engine: {e}", exc_info=True)

        # Clear message store (this clears all queues)
        if self.store:
            try:
                self.store.clear()
                logger.debug("Message store cleared")
            except Exception as e:
                logger.error(f"Error clearing message store: {e}", exc_info=True)

        # Clear thread lists and config
        self._write_threads = []
        self._read_threads = []
        self._original_config = None
        self._command_consumer = None
        
        logger.info("EngineRunner stopped and cleaned up")

    def snapshot(self) -> Dict[str, Any]:
        snapshot = self.engine.snapshot()
        if self._original_config:
            snapshot["config"] = self._original_config
        return snapshot

    async def manual_step(self, ticks: int) -> Dict[str, Any]:
        result = self.engine.step(ticks)
        self._process_sensor_messages(result.get("sensor_messages", {}))
        self._process_sector_states(result.get("sector_states", []))
        self._process_agent_states(result.get("agent_states", []))
        self._process_events(result.get("events", []))
        return result
