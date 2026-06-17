"""
Main simulation engine for FFSim according to spec section 4.

Tick lifecycle (section 4.1):
1. Snapshot currentState -> previousState
2. Propagacja pożaru
3. Aktualizacja agentów
4. Aktualizacja środowiska
5. Generacja telemetrii
6. Publikacja RabbitMQ
7. Commit nextState
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import copy
import uuid
import logging

from src.engine.rng_manager import RngManager
from src.engine.models.sector import Sector, SectorState, SectorType
from src.engine.models.fire_propagation import FirePropagation, Wind, FirePropagationConfig
from src.engine.models.event_queue import EventQueue
from src.engine.agent_manager import AgentManager, AgentEvent, AgentEventType
from src.engine.sensors import SensorArray, SensorType, SensorReading
from src.messaging.rabbitmq_publisher import RabbitMQPublisher

logger = logging.getLogger(__name__)

# Progi, powyżej których odczyt sensora oznacza wykryty pożar. Baseline +
# szum ich nie przebija; dopiero dorzut z płonącego sektora (sensors.py) tak.
DETECT_CO2_PPM = 800.0     # baseline 400 ppm
DETECT_PM25 = 100.0        # baseline 35 µg/m³
DETECT_TEMP_C = 45.0       # baseline ~20 °C


@dataclass
class SimulationSnapshot:
    """Immutable snapshot of simulation state (values frozen via copy semantics, not frozen=True)."""
    
    simulation_id: str
    tick: int
    simulation_time: float  # Logical clock: tick * tick_interval (seconds)
    
    # Map state (immutable)
    sectors: Dict[int, Sector] = field(default_factory=dict)
    
    # Environment
    wind: Wind = field(default_factory=Wind)
    global_temperature: float = 20.0
    
    # RNG state (for determinism)
    rng_state: Dict[str, Any] = field(default_factory=dict)
    
    # Event audit trail
    events: EventQueue = field(default_factory=EventQueue)
    
    def clone(self) -> "SimulationSnapshot":
        """Create deep copy of snapshot."""
        return copy.deepcopy(self)
    
    # Agents (mutated in place by AgentManager; snapshotted in engine.snapshot())
    agents: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # rng_state contains numpy state tuples which aren't JSON-serializable;
        # expose just the seed and call count for the snapshot endpoint.
        rng_summary = {
            "seed": self.rng_state.get("seed"),
            "call_count": self.rng_state.get("call_count"),
        }
        return {
            "simulation_id": self.simulation_id,
            "tick": self.tick,
            "simulation_time": self.simulation_time,
            "sectors": {sid: s.to_dict() for sid, s in self.sectors.items()},
            "wind": {
                "speed": self.wind.speed,
                "direction_degrees": self.wind.direction_degrees,
            },
            "global_temperature": self.global_temperature,
            "rng_state": rng_summary,
            "events": self.events.to_dict(),
            "agents": self.agents,
        }


class SimulationEngine:
    """
    Main fire simulation engine with immutable tick model.
    
    Implements deterministic, reproducible fire simulation.
    """
    
    def __init__(self,
                 forest_map: Dict[int, Sector],
                 rng: Optional[RngManager] = None,
                 fire_config: Optional[FirePropagationConfig] = None,
                 simulation_id: Optional[str] = None,
                 tick_interval: float = 1.0,
                 agent_manager: Optional[AgentManager] = None):
        """
        Initialize simulation engine.
        
        Args:
            forest_map: Dictionary of sector_id -> Sector
            rng: RNG manager (if None, created with random seed)
            fire_config: Fire propagation configuration
            simulation_id: Simulation UUID (if None, generated)
            tick_interval: Time per tick in seconds (for logical clock)
        """
        self.rng = rng or RngManager()
        self.fire_propagation = FirePropagation(self.rng, fire_config)
        
        self.forest_map = forest_map
        self.map_rows = max(s.row for s in forest_map.values()) + 1
        self.map_cols = max(s.column for s in forest_map.values()) + 1
        
        self.simulation_id = simulation_id or str(uuid.uuid4())
        self.tick_count = 0
        self.tick_interval = tick_interval
        
        # Build sector adjacency map for 4-neighborhood (section 5.3)
        self._build_adjacency_map()

        # Agent manager (spec section 4)
        self.agent_manager = agent_manager or AgentManager()

        # Sensor array (spec section 5.2.2)
        self.sensor_array = SensorArray(rng=self.rng)

        # RabbitMQ publisher (spec section 5.2)
        self.rabbitmq_publisher = RabbitMQPublisher()

        # metrics tracker (ustawiany z zewnątrz przez EngineHost gdy experimentLog jest aktywny)
        self.metrics_tracker = None

        # Wykrywanie pożaru (Krok 3): support dostaje stan sektora dopiero po
        # jego wykryciu — przez sensor przekraczający próg albo patrol w pobliżu.
        # Mapa operatora dalej widzi prawdę, bramkujemy tylko feed do FFSup.
        # Gdy detection_enabled=False support znów ma pełną wiedzę (stare zachowanie).
        self.detection_enabled = True
        self._detected_sectors: set = set()

        # Historia stanów do cofania kroku (sektory + agenci + RNG). Trzymana
        # z ograniczeniem, żeby nie rosła w nieskończoność przy długim biegu.
        self._history: List[Dict[str, Any]] = []
        self.max_history = 1000

        # Current state
        self.current_snapshot: Optional[SimulationSnapshot] = None
        self.last_events: List[AgentEvent] = []
    
    def _build_adjacency_map(self) -> None:
        """Build adjacency map for 4-neighborhood (North, East, South, West).
        
        O(N) complexity using position_map for O(1) lookup.
        """
        # Build position map (row, col) -> sector_id for O(1) lookup
        position_map: Dict[tuple, int] = {}
        for sector_id, sector in self.forest_map.items():
            position_map[(sector.row, sector.column)] = sector_id
        
        # Build adjacency using O(1) lookups
        self.adjacency_map: Dict[int, List[Tuple[int, int]]] = {}
        
        for sector_id, sector in self.forest_map.items():
            neighbors = []
            
            # Check all 4 directions: North, East, South, West
            for dr, dc in FirePropagation.DIRECTIONS:
                neighbor_row = sector.row + dr
                neighbor_col = sector.column + dc
                
                # O(1) lookup instead of O(N) search
                if (neighbor_row, neighbor_col) in position_map:
                    neighbor_id = position_map[(neighbor_row, neighbor_col)]
                    neighbors.append((neighbor_id, (dr, dc)))
            
            self.adjacency_map[sector_id] = neighbors
    
    def initialize(self, seed: Optional[int] = None, initial_wind: Optional[Wind] = None) -> SimulationSnapshot:
        """
        Initialize simulation with optional seed and wind.
        
        Args:
            seed: Optional random seed
            initial_wind: Initial wind state
        
        Returns:
            Initial snapshot
        """
        if seed is not None:
            self.rng = RngManager(seed=seed)
            self.fire_propagation.rng = self.rng

        # Świeży przebieg: nic jeszcze nie wykryte, pusta historia cofania
        self._detected_sectors = set()
        self._history = []

        # Create initial snapshot
        self.current_snapshot = SimulationSnapshot(
            simulation_id=self.simulation_id,
            tick=0,
            simulation_time=0.0 * self.tick_interval,  # Logical clock
            sectors={sid: s.clone() for sid, s in self.forest_map.items()},
            wind=initial_wind or Wind(speed=0.0, direction_degrees=0.0),
            global_temperature=20.0,
            rng_state=self.rng.get_state(),
            agents=self.agent_manager.to_dict(),
        )
        
        return self.current_snapshot
    
    def step(self) -> SimulationSnapshot:
        """
        Execute one tick according to FFSim spec section 4.1.
        
        Lifecycle:
        1. Snapshot currentState -> previousState
        2. Propagacja pożaru
        3. Aktualizacja agentów (TODO)
        4. Aktualizacja środowiska
        5. Generacja telemetrii (TODO)
        6. Publikacja RabbitMQ (TODO)
        7. Commit nextState
        
        Returns:
            New snapshot after tick
        """
        if self.current_snapshot is None:
            raise RuntimeError("Simulation not initialized. Call initialize() first.")

        # Zapis stanu sprzed tego kroku do historii cofania. Agentów kopiujemy
        # zanim process_tick ich zmodyfikuje, a RNG jest już w snapshocie.
        self._history.append({
            "snapshot": self.current_snapshot.clone(),
            "agent_manager": copy.deepcopy(self.agent_manager),
            "detected": set(self._detected_sectors),
        })
        if len(self._history) > self.max_history:
            self._history.pop(0)

        # Phase 1: Create immutable snapshot of previous state
        previous_snapshot = self.current_snapshot.clone()
        
        # Phase 2: Fire propagation
        next_sectors = self._phase_fire_propagation(previous_snapshot)

        # Phase 3: Agent updates (spec section 2.7 step 2)
        self.last_events = self.agent_manager.process_tick(
            next_sectors=next_sectors,
            previous_sectors=previous_snapshot.sectors,
            current_tick=self.tick_count + 1,
        )
        if self.metrics_tracker:
            for event in self.last_events:
                if event.event_type == AgentEventType.BRIGADE_ARRIVED:
                    self.metrics_tracker.on_brigade_arrived(event.agent_id, self.tick_count + 1)

        # Phase 4: Environment updates (random wind walk, spec section 3.4)
        next_wind, next_temperature = self._phase_environment_update(previous_snapshot)
        
        # Phase 5: Telemetry generation (spec section 5.2)
        # Milisekundy, nie mikrosekundy — backend mapuje timestamp na java.util.Date,
        # które potrafi nie sparsować 6-cyfrowej części ułamkowej i po cichu odrzucić
        # rekord agenta (pusty batch → brak ruchu kropek na mapie).
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
        telemetry_data = self._phase_telemetry_generation(
            next_sectors=next_sectors,
            previous_sectors=previous_snapshot.sectors,
            wind=next_wind,
            temperature=next_temperature,
            timestamp=timestamp
        )
        
        # Phase 6: RabbitMQ publication (spec section 5.2)
        self._phase_rabbitmq_publication(telemetry_data)
        
        # Phase 7: Commit next state
        self.tick_count += 1
        self.current_snapshot = SimulationSnapshot(
            simulation_id=self.simulation_id,
            tick=self.tick_count,
            simulation_time=self.tick_count * self.tick_interval,  # Logical clock
            sectors=next_sectors,
            wind=next_wind,
            global_temperature=next_temperature,
            rng_state=self.rng.get_state(),
            agents=self.agent_manager.to_dict(),
        )
        
        return self.current_snapshot

    def step_back(self) -> bool:
        """
        Cofa symulację o jeden krok, przywracając stan z historii (sektory,
        agenci, RNG i zbiór wykrytych sektorów). Zwraca False gdy nie ma już
        czego cofać.
        """
        if not self._history:
            return False

        record = self._history.pop()
        self.current_snapshot = record["snapshot"]
        self.agent_manager = record["agent_manager"]
        self._detected_sectors = record["detected"]
        self.tick_count = self.current_snapshot.tick

        # Przywrócenie RNG, żeby ponowne kroki w przód były spójne ze stanem.
        try:
            self.rng.set_state(self.current_snapshot.rng_state)
            self.fire_propagation.rng = self.rng
        except Exception:
            logger.warning("Nie udało się przywrócić stanu RNG przy cofaniu kroku")

        return True

    def publish_current_state(self) -> None:
        """
        Generuje i publikuje telemetrię z bieżącego snapshotu, bez wykonywania
        kroku. Używane po cofnięciu, żeby backend i mapa odświeżyły się do
        przywróconego stanu.
        """
        if self.current_snapshot is None:
            return
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
        sectors = self.current_snapshot.sectors
        telemetry = self._phase_telemetry_generation(
            next_sectors=sectors,
            previous_sectors=sectors,
            wind=self.current_snapshot.wind,
            temperature=self.current_snapshot.global_temperature,
            timestamp=timestamp,
        )
        self._phase_rabbitmq_publication(telemetry)

    def _phase_fire_propagation(self, previous_snapshot: SimulationSnapshot) -> Dict[int, Sector]:
        """
        Phase 2: Fire propagation (section 4.2).
        
        For each burning sector:
        - Spread fire to adjacent sectors
        - Update fire level
        - Consume fuel
        - Check burnout and extinguishment
        """
        next_sectors = {sid: s.clone() for sid, s in previous_snapshot.sectors.items()}
        
        # Iterate over all burning sectors in previous state
        for sector_id, prev_sector in previous_snapshot.sectors.items():
            if not prev_sector.is_burning():
                continue
            
            next_sector = next_sectors[sector_id]
            
            # Attempt to spread fire to neighbors
            for neighbor_id, (dr, dc) in self.adjacency_map.get(sector_id, []):
                neighbor_prev = previous_snapshot.sectors[neighbor_id]
                neighbor_next = next_sectors[neighbor_id]
                
                # Check ignition probability
                ignites = self.fire_propagation.attempt_ignition(
                    target_sector=neighbor_prev,
                    neighbor_sector=prev_sector,
                    wind=previous_snapshot.wind,
                    from_row=prev_sector.row,
                    from_col=prev_sector.column,
                    to_row=neighbor_prev.row,
                    to_col=neighbor_prev.column,
                    global_temperature=previous_snapshot.global_temperature,
                )
                
                if ignites:
                    # FSM validation: only ignite DORMANT sectors
                    if neighbor_next.is_flammable():
                        neighbor_next.state = SectorState.BURNING
                        neighbor_next.fire_level = 0.1  # Initial fire level
                        if self.metrics_tracker:
                            self.metrics_tracker.on_ignition(neighbor_id, self.tick_count + 1)
                    # else: log warning if trying to re-ignite already burning sector
            
            # Update fire level per spec section 2.5.1 R3:
            # ∆ℓ = spreadRate · k_sector (k_sector = flammability coefficient)
            sector_multiplier = prev_sector.get_flammability_coefficient()

            next_sector.fire_level = self.fire_propagation.update_fire_level(
                prev_sector,
                sector_multiplier=sector_multiplier,
            )
            
            # Consume fuel (section 6.3)
            next_sector.fuel = self.fire_propagation.update_fuel(prev_sector)
            
            # Update burn level (tracking cumulative burning)
            next_sector.burn_level = self.fire_propagation.update_burn_level(prev_sector)
            
            # Check burnout (section 6.4)
            if self.fire_propagation.check_burnout(next_sector):
                next_sector.state = SectorState.ASH
                next_sector.fire_level = 0.0
            
            # Check extinguishment (spec section 2.5.1 R5: extinguishLevel ≥ ethr → Ext)
            if self.fire_propagation.check_extinguishment(next_sector):
                next_sector.state = SectorState.EXTINGUISHED
                next_sector.fire_level = 0.0
        
        return next_sectors
    
    def _phase_environment_update(self, previous_snapshot: SimulationSnapshot) -> Tuple[Wind, float]:
        """
        Phase 4: Environment updates (spec section 3.4).

        "W każdym kroku derywacji prędkość i kierunek wiatru ewoluują losowo
         w małych granicach, co symuluje naturalne fluktuacje warunków atmosferycznych."

        Small random walk on wind speed and direction using central RNG.
        """
        prev_wind = previous_snapshot.wind

        # Small bounded random perturbations (spec: "w małych granicach")
        speed_delta = self.rng.uniform(-1.0, 1.0)          # ±1 km/h per tick
        direction_delta = self.rng.uniform(-5.0, 5.0)      # ±5° per tick

        new_speed = max(0.0, min(80.0, prev_wind.speed + speed_delta))
        new_direction = (prev_wind.direction_degrees + direction_delta) % 360.0

        next_wind = Wind(speed=new_speed, direction_degrees=new_direction)
        return next_wind, previous_snapshot.global_temperature
    
    def get_snapshot(self) -> SimulationSnapshot:
        """Get current simulation snapshot."""
        if self.current_snapshot is None:
            raise RuntimeError("Simulation not initialized")
        return self.current_snapshot
    
    def get_sector_state(self, sector_id: int) -> Dict[str, Any]:
        """Get current state of specific sector."""
        if self.current_snapshot is None:
            raise RuntimeError("Simulation not initialized")
        
        sector = self.current_snapshot.sectors[sector_id]
        return sector.to_dict()
    
    def ignite_sector(self, sector_id: int) -> bool:
        """
        Manually ignite a sector (for testing/initialization).
        
        Args:
            sector_id: ID of sector to ignite
        
        Returns:
            True if successfully ignited, False if not flammable
        """
        if self.current_snapshot is None:
            raise RuntimeError("Simulation not initialized")
        
        sector = self.current_snapshot.sectors[sector_id]
        if not sector.is_flammable():
            return False

        sector.state = SectorState.BURNING
        sector.fire_level = 0.1
        return True

    def ignite_random_sector(self) -> Optional[int]:
        """
        Losowo wybiera palny sektor i go podpala (spec, sekcja "Przepływ danych":
        symulator sam wybiera sektor, w którym rozpocznie się pożar).

        Wybór idzie przez centralny RNG, więc przy tym samym seedzie zapłon
        jest deterministyczny.

        Returns:
            ID podpalonego sektora albo None gdy nie ma palnych sektorów.
        """
        if self.current_snapshot is None:
            raise RuntimeError("Simulation not initialized")

        flammable = [sid for sid, s in self.current_snapshot.sectors.items()
                     if s.is_flammable()]
        if not flammable:
            return None

        chosen = flammable[self.rng.randint(0, len(flammable))]
        self.ignite_sector(chosen)
        return chosen

    def _phase_telemetry_generation(self,
                                     next_sectors: Dict[int, Sector],
                                     previous_sectors: Dict[int, Sector],
                                     wind: Wind,
                                     temperature: float,
                                     timestamp: str) -> Dict[str, Any]:
        """
        Phase 5: Telemetry generation (spec section 5.2).
        
        Generates:
        - Sector state telemetry (full and fast variant)
        - Sensor readings
        - Agent state telemetry
        
        Args:
            next_sectors: Updated sectors after fire propagation
            previous_sectors: Previous sector states
            wind: Current wind state
            temperature: Current temperature
            timestamp: ISO timestamp
        
        Returns:
            Telemetry data dict with keys: sectors, sensors, agents
        """
        telemetry = {
            "sectors": [],
            "sectors_fast": [],  # Only changed sectors
            "sensors": [],
            "agents": [],
        }
        
        # Odległość każdego sektora do najbliższego pożaru (BFS wieloźródłowy z
        # palących się sektorów). Steruje poziomem zagrożenia, dzięki czemu
        # ryzyko tworzy gradient wokół ognia zamiast jednolitej plamy.
        dist_to_fire = self._distances_to_fire(next_sectors)

        # Sector state telemetry (spec 5.2.1).
        # Silnik trzyma poziomy w skali 0-1, telemetria FFSup/FFVis oczekuje
        # 0-100 (alpha na mapie, requiredBrigades = ceil(fireLevel/3)).
        for sector_id, sector in next_sectors.items():
            sector_telemetry = {
                "sectorId": sector_id,
                "fireLevel": sector.fire_level * 100.0,
                "burnLevel": sector.burn_level * 100.0,
                "extinguishLevel": sector.extinguish_level * 100.0,
                "fireState": sector.get_fire_state_name(),
                "threatLevel": sector.get_threat_level(dist_to_fire.get(sector_id)),
            }
            telemetry["sectors"].append(sector_telemetry)
            
            # Fast variant: only if state changed
            prev_sector = previous_sectors[sector_id]
            if (prev_sector.fire_level != sector.fire_level or
                prev_sector.burn_level != sector.burn_level or
                prev_sector.extinguish_level != sector.extinguish_level or
                prev_sector.state != sector.state):
                telemetry["sectors_fast"].append(sector_telemetry)
        
        # Sensor readings (spec 5.2.2). Odczyty rosną na płonących sektorach,
        # dlatego podajemy aktualne poziomy ognia.
        sector_fire_levels = {sid: s.fire_level for sid, s in next_sectors.items()}
        sensor_readings = self.sensor_array.read_all(
            timestamp=timestamp,
            wind_speed=wind.speed,
            wind_direction=wind.direction_degrees,
            global_temperature=temperature,
            sector_fire_levels=sector_fire_levels,
        )
        for reading in sensor_readings:
            telemetry["sensors"].append(reading.to_dict())
        
        # Agent telemetry (spec 5.2.3)
        agents_dict = self.agent_manager.to_dict()

        def _loc(raw: Dict[str, Any]) -> Dict[str, float]:
            # Agent trzyma lon/lat, ale backend i frontend (animacja kropek)
            # czytają longitude/latitude. Dajemy oba klucze, żeby każdy odbiorca
            # (support, backend, front) sparsował położenie.
            lon = raw.get("lon", raw.get("longitude", 0.0))
            lat = raw.get("lat", raw.get("latitude", 0.0))
            return {"longitude": lon, "latitude": lat, "lon": lon, "lat": lat}

        # Fire brigades
        brigades = []
        for brigade_data in agents_dict.get("brigades", []):
            brigade_telemetry = {
                "fireBrigadeId": brigade_data.get("agent_id"),
                "state": brigade_data.get("state", "AVAILABLE"),
                "timestamp": timestamp,
                "location": _loc(brigade_data.get("location", {})),
                "sectorId": brigade_data.get("sector_id"),
            }
            brigades.append(brigade_telemetry)

        telemetry["agents"].append({
            "type": "fire_brigades",
            "data": brigades
        })

        # Foresters
        foresters = []
        for forester_data in agents_dict.get("foresters", []):
            forester_telemetry = {
                "foresterPatrolId": forester_data.get("agent_id"),
                "state": forester_data.get("state", "AVAILABLE"),
                "timestamp": timestamp,
                "location": _loc(forester_data.get("location", {})),
                "sectorId": forester_data.get("sector_id"),
            }
            foresters.append(forester_telemetry)
        
        telemetry["agents"].append({
            "type": "foresters",
            "data": foresters
        })

        # Aktualizacja wykrytych sektorów na podstawie sensorów i patroli.
        # Wynik (self._detected_sectors) bramkuje feed do supportu.
        self._update_detection(next_sectors, sensor_readings, foresters)

        return telemetry
    
    def _phase_rabbitmq_publication(self, telemetry_data: Dict[str, Any]) -> None:
        """
        Phase 6: RabbitMQ publication (spec section 5.2).
        
        Publishes telemetry to fire_updates exchange per spec routing keys.
        
        Args:
            telemetry_data: Telemetry dict from Phase 5
        """
        if not self.rabbitmq_publisher.available:
            logger.debug("RabbitMQ unavailable, skipping publication")
            return
        
        # Publish full sector states (spec 5.2.1)
        for sector_data in telemetry_data.get("sectors", []):
            self.rabbitmq_publisher.publish_sector_state(sector_data)
        
        # Publish fast sector states (only changed)
        for sector_data in telemetry_data.get("sectors_fast", []):
            self.rabbitmq_publisher.publish(
                routing_key="simulation.telemetry.map.sector_state_fast",
                message=sector_data
            )
        
        # Publish sensor readings (spec 5.2.2)
        for sensor_reading in telemetry_data.get("sensors", []):
            self.rabbitmq_publisher.publish_sensor_reading(
                sensor_type=sensor_reading.get("sensorType"),
                sensor_id=sensor_reading.get("sensorId"),
                location=sensor_reading.get("location"),
                data=sensor_reading.get("data"),
                timestamp=sensor_reading.get("timestamp")
            )
        
        # Publish agent states (spec 5.2.3)
        for agent_batch in telemetry_data.get("agents", []):
            agent_type = agent_batch.get("type")
            agent_data = agent_batch.get("data", [])
            
            # Publikujemy tylko wariant zbiorczy (batch). Wcześniej każdy agent
            # leciał dodatkowo osobną wiadomością na własną kolejkę, a backend
            # konsumował obie równolegle. Dwie kolejki czytane z dwóch wątków
            # nie mają gwarancji kolejności, więc spóźniona pojedyncza wiadomość
            # nadpisywała nowszą pozycję z batcha i agent "teleportował się".
            # Jedna kolejka batch = FIFO z RabbitMQ, brak wyścigu.
            if agent_type == "fire_brigades":
                self.rabbitmq_publisher.publish_fire_brigade_batch(agent_data)

            elif agent_type == "foresters":
                self.rabbitmq_publisher.publish_forester_batch(agent_data)

        # Feed dla FFSup: support konsumuje zagregowany stan na routing key
        # support.data.aggregated oraz pozycje agentów na agent_position.
        # Backend tego nie agreguje (robi to tylko dla frontendu przez SSE),
        # więc źródłem danych dla supportu jest bezpośrednio symulator.
        self._publish_support_feed(telemetry_data)

    def _distances_to_fire(self, sectors: Dict[int, Sector], max_dist: int = 3) -> Dict[int, int]:
        """
        Zwraca mapę sector_id -> odległość (w sektorach) do najbliższego
        płonącego sektora, licząc BFS wieloźródłowy po sąsiedztwie. Sektory
        dalej niż max_dist są pomijane (brak wpisu = poza zasięgiem).
        """
        dist: Dict[int, int] = {}
        queue = deque()
        for sid, s in sectors.items():
            if s.is_burning():
                dist[sid] = 0
                queue.append(sid)

        while queue:
            cur = queue.popleft()
            if dist[cur] >= max_dist:
                continue
            for neighbor_id, _ in self.adjacency_map.get(cur, []):
                if neighbor_id not in dist:
                    dist[neighbor_id] = dist[cur] + 1
                    queue.append(neighbor_id)

        return dist

    def _sensor_trips(self, reading: SensorReading) -> bool:
        """Czy odczyt sensora oznacza wykryty pożar (przekroczony próg)."""
        t = reading.sensor_type
        d = reading.data or {}
        if t == SensorType.CO2:
            return d.get("concentration", 0.0) > DETECT_CO2_PPM
        if t == SensorType.PM2_5:
            return d.get("concentration", 0.0) > DETECT_PM25
        if t == SensorType.TEMP_HUMIDITY:
            return d.get("temperature", 0.0) > DETECT_TEMP_C
        if t == SensorType.CAMERA:
            return bool(d.get("smokeDetected"))
        return False

    def _update_detection(self,
                          next_sectors: Dict[int, Sector],
                          sensor_readings: List[SensorReading],
                          foresters: List[Dict[str, Any]]) -> None:
        """
        Aktualizuje zbiór wykrytych sektorów (Krok 3).

        Sektor zostaje wykryty, gdy płonie i jednocześnie:
        - któryś sensor na nim lub na sektorze sąsiednim przekroczył próg, albo
        - patrol leśny stoi na nim lub na sektorze sąsiednim.

        Wykrycie jest zatrzaskowe (latch): raz wykryty sektor pozostaje znany
        supportowi do końca przebiegu, nawet gdy ogień przygaśnie.
        """
        if not self.detection_enabled:
            # support widzi wszystko (jak przed dołożeniem wykrywania)
            self._detected_sectors = set(next_sectors.keys())
            return

        # sektory obserwowane przez patrole: bieżący sektor patrolu + sąsiedzi
        patrol_observed: set = set()
        for f in foresters:
            sid = f.get("sectorId")
            if sid is None:
                continue
            patrol_observed.add(sid)
            for neighbor_id, _ in self.adjacency_map.get(sid, []):
                patrol_observed.add(neighbor_id)

        # sektory obserwowane przez czujniki: ten, na którym sensor przebił próg,
        # oraz jego sąsiedzi. Dym i podwyższone stężenia gazów rozchodzą się na
        # pobliskie sektory, więc czujnik na sąsiednim sektorze również potwierdza
        # pożar. Bez tego ogień musiałby dorosnąć dokładnie pod czujnikiem, żeby
        # support go zobaczył, przez co detekcja startowała z dużym opóźnieniem.
        sensor_observed: set = set()
        for reading in sensor_readings:
            if reading.sector_id is not None and self._sensor_trips(reading):
                sensor_observed.add(reading.sector_id)
                for neighbor_id, _ in self.adjacency_map.get(reading.sector_id, []):
                    sensor_observed.add(neighbor_id)

        for sid, sector in next_sectors.items():
            if sid in self._detected_sectors:
                continue
            if not sector.is_burning():
                continue
            if sid in sensor_observed or sid in patrol_observed:
                self._detected_sectors.add(sid)
                tracker = self.metrics_tracker
                if tracker is not None and hasattr(tracker, "on_detection"):
                    tracker.on_detection(sid, self.tick_count + 1)

    def _publish_support_feed(self, telemetry_data: Dict[str, Any]) -> None:
        """
        Publikuje zagregowany stan dla FFSup na support.data.aggregated.

        Support potrzebuje w jednej wiadomości i sektorów, i stanu brygad
        (bez brygad odrzuca generowanie rekomendacji jako "insufficient state").
        Walidator supportu wymaga klucza sectors/fireBrigades/foresterPatrols,
        więc agentów wysyłamy pod tymi właśnie kluczami.
        """
        message: Dict[str, Any] = {}

        # Bramkowanie wykrywaniem: sektory jeszcze niewykryte raportujemy
        # supportowi jako spokojne (DORMANT, zero ognia), więc MCTS nie wysyła
        # tam brygad zanim pożar nie zostanie zauważony przez sensor lub patrol.
        detected = self._detected_sectors
        support_sectors = []
        for s in telemetry_data.get("sectors", []):
            sid = s["sectorId"]
            if sid in detected:
                state = {
                    "fireLevel": s["fireLevel"],
                    "burnLevel": s["burnLevel"],
                    "extinguishLevel": s["extinguishLevel"],
                    "fireState": s["fireState"],
                }
            else:
                state = {
                    "fireLevel": 0.0,
                    "burnLevel": 0.0,
                    "extinguishLevel": 0.0,
                    "fireState": SectorState.DORMANT.value,
                }
            support_sectors.append({"sectorId": sid, "state": state})

        if support_sectors:
            message["sectors"] = support_sectors

        for batch in telemetry_data.get("agents", []):
            if batch.get("type") == "fire_brigades":
                message["fireBrigades"] = batch.get("data", [])
            elif batch.get("type") == "foresters":
                message["foresterPatrols"] = batch.get("data", [])

        if message:
            self.rabbitmq_publisher.publish(
                routing_key="support.data.aggregated",
                message=message,
            )
