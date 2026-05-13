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
import copy
import uuid

from src.engine.rng_manager import RngManager
from src.engine.models.sector import Sector, SectorState, SectorType
from src.engine.models.fire_propagation import FirePropagation, Wind, FirePropagationConfig
from src.engine.models.event_queue import EventQueue


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
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
            "rng_state": self.rng_state,
            "events": self.events.to_dict(),
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
                 tick_interval: float = 1.0):
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
        
        # Current state
        self.current_snapshot: Optional[SimulationSnapshot] = None
    
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
        
        # Create initial snapshot
        self.current_snapshot = SimulationSnapshot(
            simulation_id=self.simulation_id,
            tick=0,
            simulation_time=0.0 * self.tick_interval,  # Logical clock
            sectors={sid: s.clone() for sid, s in self.forest_map.items()},
            wind=initial_wind or Wind(speed=0.0, direction_degrees=0.0),
            global_temperature=20.0,
            rng_state=self.rng.get_state(),
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
        
        # Phase 1: Create immutable snapshot of previous state
        previous_snapshot = self.current_snapshot.clone()
        
        # Phase 2: Fire propagation
        next_sectors = self._phase_fire_propagation(previous_snapshot)
        
        # Phase 3: Agent updates (TODO - agents from existing agent_manager)
        # next_sectors = self._phase_agent_updates(next_sectors)
        
        # Phase 4: Environment updates
        next_wind, next_temperature = self._phase_environment_update(previous_snapshot)
        
        # Phase 5: Telemetry generation (TODO - integrate with messaging)
        # telemetry = self._generate_telemetry(next_sectors)
        
        # Phase 6: RabbitMQ publication (TODO - integrate with messaging)
        # self._publish_telemetry(telemetry)
        
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
        )
        
        return self.current_snapshot
    
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
                    # else: log warning if trying to re-ignite already burning sector
            
            # Update fire level (section 6.2)
            # Separate multipliers: sector effect only
            sector_multiplier = 1.0 / prev_sector.get_flammability_coefficient()
            sector_multiplier = max(0.1, min(sector_multiplier, 2.0))  # Clamp
            
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
            
            # Check extinguishment (section 6.5)
            if self.fire_propagation.check_extinguishment(next_sector):
                next_sector.state = SectorState.ASH
                next_sector.fire_level = 0.0
        
        return next_sectors
    
    def _phase_environment_update(self, previous_snapshot: SimulationSnapshot) -> Tuple[Wind, float]:
        """
        Phase 4: Environment updates (section 7.2).
        
        Currently stub - to be extended with wind dynamics and temperature evolution.
        """
        # For now, return unchanged wind and temperature
        # TODO: Implement wind dynamics and temperature evolution
        return previous_snapshot.wind.clone() if hasattr(previous_snapshot.wind, 'clone') else previous_snapshot.wind, previous_snapshot.global_temperature
    
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
