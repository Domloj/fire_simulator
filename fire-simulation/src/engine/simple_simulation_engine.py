import random
import logging
import time
from typing import Dict, Any, List, Optional

from src.settings.communucation_settings import CommunicationSettings
from src.settings.simulation_settings import SimulationSettings

from src.engine.base import SimulationEngine
from src.engine.models.map.forest_map import ForestMap
from src.engine.models.map.sector import Sector
from src.engine.models.map.fire_state import FireState
from src.engine.models.environment.wind import Wind
from src.engine.models.environment.fire_spread import calculate_beta
from src.engine.agent_manager.agent_manager import AgentManager

logger = logging.getLogger(__name__)

class SimpleSimulationEngine(SimulationEngine):
    '''
    A simple simulation engine for fire simulation.
    Restored to full complex version with all features.
    '''
    def __init__(
        self, 
        simulation_settings: SimulationSettings       = SimulationSettings(), 
        communication_settings: CommunicationSettings = CommunicationSettings()
    ):
        logger.info("Initializing SimpleSimulationEngine (Complex Version)")
        
        self.simulation_settings: SimulationSettings        = simulation_settings
        self.communication_settings: CommunicationSettings  = communication_settings 

        ''' Engine state '''
        self.config: Optional[dict]                         = None
        self.agents_manager: Optional[AgentManager]         = None
        self.wind: Optional[Wind]                           = None
        self.all_sectors: List[Sector]                      = []
        self.sectors_on_fire: List[Sector]                  = []
        self._tick_count: float                             = 0
        self._agent_tick_count: int                         = 0
        self._running: bool                                 = False 
        self._map: Optional[ForestMap]                      = None

        self._sector_update_interval: int     = simulation_settings.sector_update_interval
        self._agent_updates_per_sim_tick: int = int(simulation_settings.agent_updates_per_sim_tick)
        self._agent_telemetry_period_s: float = 1.0
        self._last_agent_telemetry_ts: float  = 0.0

    async def load_config(self, configuration: dict) -> None:
        logger.info("Loading configuration into SimpleSimulationEngine")

        try:
            self.config = configuration
            self._map = ForestMap.from_conf(configuration)
            self._tick_count = 0
            self._agent_tick_count = 0

            self.agents_manager = AgentManager(
                forest_map    = self._map, 
                message_store = None,
                engine        = self)
            
            self.speed_factor = 1.0
            self.all_sectors = [s for row in self._map.sectors for s in row]
            self.wind = Wind()
            
            if not self.sectors_on_fire:
                rows = self._map._rows
                cols = self._map._columns

                '''
                    Start fires at the four corners of the map.
                    This is the easiest simulation scenario to observe fire spread.
                '''
                fire_positions = [
                    (0, 0), 
                    (0, cols - 1),
                    (rows - 1, 0),
                    (rows - 1, cols - 1),  
                ]

                for row, col in fire_positions:
                    if 0 <= row < rows and 0 <= col < cols:
                        self.start_new_fire_sync(row, col)

                logger.info(f"Started {len(self.sectors_on_fire)} initial fires at map corners")

            logger.info("ForestMap created: %dx%d sectors", self._map._rows, self._map._columns)
            logger.info("AgentManager initialized with %d agents", len(self.agents_manager._agents))

        except Exception as e:
            logger.error("Failed to load configuration: %s", e)
            raise e

    async def start(self) -> None:
        if not self._map:
            raise ValueError("Configuration not loaded. Call load_config first.")
        self._running = True
        logger.info("Simulation engine started")

    async def stop(self) -> None:
        self._running = False
        self.sectors_on_fire = []
        self._tick_count = 0
        self._agent_tick_count = 0
        self.config = None
        self.all_sectors = []
        self._map = None

        if self.agents_manager:
            self.agents_manager._agents.clear()
            self.agents_manager._brigades.clear()
            self.agents_manager._patrols.clear()
            self.agents_manager._agent_sectors.clear()

        self.agents_manager = None
        logger.info("Simulation engine stopped and state reset")

    async def pause(self) -> None:
        self._running = False
        logger.info("Simulation engine paused")

    def set_speed_factor(self, factor: float) -> None:
        if factor <= 0:
            raise ValueError("speed_factor must be > 0")
        self.speed_factor = float(factor)
        
    def start_new_fire_sync(self, row: int, column: int) -> None:
        if not self._map: return
        try:
            sector = self._map.sectors[row][column]
            if sector.fire_state is FireState.INACTIVE:
                sector.update_fire(FireState.ACTIVE, random.randint(5, 20))
                self.sectors_on_fire.append(sector)
                logger.info(f"New fire started at sector ({row}, {column})")
        except Exception as e:
            logger.warning(f"Failed to start fire at ({row}, {column}): {e}")

    def step(self, ticks: int = 1) -> Dict[str, Any]:
        logger.info(f"Engine step called for {ticks} ticks (tick_count={self._tick_count})")
        out_messages: Dict[str, List[Any]] = {}
        sector_states: List[Any]           = []
        sector_states_fast: List[Any]      = []
        events: List[Any]                  = []
        agent_states: List[Any]            = []

        if not (self._map and self.wind and self.agents_manager):
            logger.warning("Step called but engine not fully initialized")
            return {"tick": self._tick_count, "sensor_messages": {}, "sector_states": [], "agent_states": [], "events": []}

        for tick_idx in range(ticks):
            logger.debug(f"Processing tick {tick_idx + 1}/{ticks}")
            self._tick_count += 1
            self._agent_tick_count += 1

            ''' 
                Agents tick counter & simulation tick counter.
                For now, 1 sim tick = 100 agents tick updates.
            '''
            tick_delta = self.simulation_settings.tick_interval
            sub_update_count = self._agent_updates_per_sim_tick
            sub_delta = tick_delta / sub_update_count
            logger.debug(f"Tick delta: {tick_delta}, sub_update_count: {sub_update_count}, sub_delta: {sub_delta}")

            '''
                Update agents in smaller sub-steps for smoother simulation.
                Telemetry is enabled so backend/support/frontend see live positions.
            '''
            logger.debug(f"Starting agent updates: {sub_update_count} sub-updates")
            for i in range(sub_update_count):
                if i % 10 == 0:
                    logger.debug(f"Agent update {i}/{sub_update_count}")
                self.agents_manager.update(sub_delta, publish_telemetry=True)
            logger.debug(f"Finished agent updates")

            logger.debug("Getting agent states")
            agent_states = self.agents_manager.get_agent_states()
            logger.debug("Flushing telemetry")
            try:
                self.agents_manager.flush_telemetry()
                logger.debug("Telemetry flushed")
            except Exception:
                logger.exception("Error flushing agent telemetry")
                pass

            ''' 
                Update actual simulation state: fires, sectors, sensors, etc.
                Sector updates are throttled by _sector_update_interval to slow down fire spread relative to agent updates.
            '''
            logger.debug("Checking sector update")
            sector_update_due = (self._sector_update_interval > 0) and (self._tick_count % self._sector_update_interval == 0)
            logger.debug(f"Sector update due: {sector_update_due}")

            if sector_update_due:
                self._map.update_extinguish_levels()

            agent_states = self.agents_manager.get_agent_states()

            for sector in self.all_sectors:
                has_agents = sector._number_of_fire_brigades > 0 or sector._number_of_forester_patrols > 0
                if has_agents and sector.is_modified:
                    sector_states_fast.append(sector.make_sector_json())

            new_sectors_on_fire       = []

            if sector_update_due:
                for sector in self.all_sectors:
                    sector.update_sector()

                self.sectors_on_fire = [s for s in self.all_sectors if s.fire_state is FireState.ACTIVE]

                for sector in self.sectors_on_fire:
                    for neighbour, direction in self._map.get_adjacent_sectors(sector):
                        if neighbour.fire_state is FireState.INACTIVE:
                            base_prob = calculate_beta(self.wind, neighbour.sector_type, direction)
                            spread_prob = max(0.0, min(1.0, base_prob * self.simulation_settings.fire_spread_prob_multiplier))
                            if random.random() < spread_prob:
                                neighbour.start_fire()
                                new_sectors_on_fire.append(neighbour)

                self.wind.update_wind()
            else:
                # Even when skipping sector updates, wind can still change slowly
                self.wind.update_wind()
            ''' 
                Start new fire if no fires left. 
                This was in original simulation engine, idk if this should be here.
            '''
            if len(self.sectors_on_fire) == 0:
                if self._agent_tick_count == 1 or random.random() < 0.1:
                    row = self._map._rows // 2
                    col = self._map._columns // 2
                    self.start_new_fire_sync(row, col)

            sectors_for_sensors = set()
            sectors_for_sensors.update(self.agents_manager._agent_sectors.get(aid) for aid in self.agents_manager._agents)
            sectors_for_sensors.discard(None)

            ''' 
                Update sensors for all sectors. 
                Sectors telemetry should be updated if sector either has agents, is modified or is active.
                There theoretically Forester Patrols should be important, patrolling sectors collecting telemetry.
                BUT: This is hard to model, and im lacking IQ & patience to do it.
            '''
            for sector in self.all_sectors:
                has_agents = sector._number_of_fire_brigades > 0 or sector._number_of_forester_patrols > 0
                if sector.fire_state == FireState.ACTIVE or sector.is_modified or has_agents:
                    sectors_for_sensors.add(sector)

            logger.debug(f"Updating sensors for {len(sectors_for_sensors)} sectors")
            for sector in sectors_for_sensors:
                sector_sensor_data = sector.update_sensors()
                for sensor_type, sensor_list in sector_sensor_data.items():
                    out_messages.setdefault(sensor_type, []).extend(sensor_list)

                has_agents = sector._number_of_fire_brigades > 0 or sector._number_of_forester_patrols > 0
                if sector.is_modified or has_agents:
                    sector_states.append(sector.make_sector_json())
                    if sector.is_modified:
                        sector.reset_modified_flag()
            logger.debug("Finished updating sensors")

        logger.info(f"Engine step finished for {ticks} ticks (tick_count={self._tick_count})")

        return {
            "tick": self._tick_count,
            "agent_tick": self._agent_tick_count,
            "sensor_messages": out_messages,
            "sector_states": sector_states,
            "sector_states_fast": sector_states_fast,
            "agent_states": agent_states,
            "events": events
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "tick": self._tick_count,
            "agent_tick": self._agent_tick_count,
            "running": self._running,
            "fire_count": len(self.sectors_on_fire),
            "total_sectors": len(self.all_sectors),
            "config_loaded": self.config is not None,
            "speed_factor": getattr(self, 'speed_factor', 1.0),
            "sector_update_interval": self._sector_update_interval
        }

    def is_running(self) -> bool:
        return self._running
