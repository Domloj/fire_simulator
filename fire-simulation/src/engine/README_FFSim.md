# FFSim Fire Propagation Engine - Developer Guide

## Overview

This document describes the **new FFSim fire propagation engine** according to spec sections 2-6. It replaces the old `fire_spread.py` and `simple_simulation_engine.py` with a clean, deterministic physics-based simulation.

**Key Architecture Principles:**

- **Determinism (Spec 2.1):** Identical seed + config + command order = identical simulation
- **Immutable Tick Model (Spec 2.2):** `currentState → nextState`, no in-place mutations
- **Single RNG (Spec 2.3):** All randomness from one `RngManager`, state included in snapshots
- **7-Phase Tick Lifecycle (Spec 4.1):** Snapshot → Propagation → Agents → Environment → Telemetry → RabbitMQ → Commit

---

## Module Architecture

### 1. **RngManager** (`src/engine/rng_manager.py`)

**Purpose:** Single source of truth for all randomness. Enables 100% reproducible simulations.

**Key Features:**

- Uses NumPy's `RandomState` for deterministic generation
- Tracks call count for debugging
- State management via `get_state()` / `set_state()` for snapshots
- All methods return deterministic values with given seed

**Methods:**

```python
rng = RngManager(seed=42)

# Random floats
value = rng.random()           # [0, 1)
value = rng.uniform(0, 10)     # [0, 10)
value = rng.normal(0, 1)       # Normal distribution

# Random integers
value = rng.randint(0, 100)    # [0, 100)
choices = rng.choice([1,2,3], size=2)  # Select from array

# State management (for snapshots)
state = rng.get_state()        # Get current RNG state
rng.set_state(state)           # Restore RNG state
```

**Usage in Simulation:**

```python
# Initialize with seed for reproducibility
seed = 12345
rng = RngManager(seed=seed)

# Use in fire propagation
if rng.random() < ignition_probability:
    fire_spreads()

# Save RNG state to snapshot
snapshot.rng_state = rng.get_state()
```

**Critical Rule:** Never use `random.random()`, `np.random.random()`, or `time`-based generation outside this class.

---

### 2. **Sector** (`src/engine/models/sector.py`)

**Purpose:** Domain entity representing a single forest sector with fire physics state.

**L-System State Machine (Spec 5.1):**

```
F (DORMANT)   → sektor niepalący się
B (BURNING)   → sektor płonący
A (ASH)       → sektor wypalony/ugaszony (nieodwracalny)
W (WATER)     → sektor niepalny
```

**State Transitions:**

```
DORMANT  → BURNING  (via ignition)
BURNING  → ASH      (via burnout when fuel ≤ 0)
BURNING  → ASH      (via extinguishment when extinguish_level ≥ threshold)
WATER    → (no transitions, permanent)
```

**Parameters (Spec 5.2):**

- `moisture: [0, 1]` - wilgotność (reduces ignition)
- `fuel: [0, 1]` - paliwo (must consume to burnout)
- `fire_level: [0, 1]` - intensywność ognia (grows as sector burns)
- `burn_level: [0, 1]` - spalanie (cumulative tracking)
- `extinguish_level: [0, 1]` - gaszenie (from fire brigades)
- `temperature: ℝ` - temperatura (affects ignition)

**Flammability Coefficients (Spec 5.2):**

```python
α_coefficients = {
    SectorType.FIELD:       1.5,    # najłatwopalny
    SectorType.FALLOW:      1.2,
    SectorType.CONIFEROUS:  1.2,
    SectorType.MIXED:       1.0,
    SectorType.DECIDUOUS:   0.8,
    SectorType.WATER:       0.0,    # niepalny
    SectorType.UNTRACKED:   1.0,
}
```

**Key Methods:**

```python
# Check state
if sector.is_burning():
    print("Currently burning")

if sector.is_flammable():
    print("Can catch fire")

# Get vegetation properties
alpha = sector.get_flammability_coefficient()  # Affects fire spread

# Serialization
dict_data = sector.to_dict()
sector = Sector.from_dict(dict_data)

# Immutability
sector_copy = sector.clone()  # Deep copy
```

**Validation:**
All `[0,1]` parameters are validated in `__post_init__()`. Temperature is unbounded (ℝ).

---

### 3. **FirePropagation** (`src/engine/models/fire_propagation.py`)

**Purpose:** Physics engine for fire spread, fuel consumption, and state transitions.

**Wind Model (Spec 6.1):**

```
wind_component = 1 + α|w|cosθ

Where:
- α: wind coefficient (tunable)
- |w|: wind speed
- cosθ: cosine of angle between wind direction and spread direction
  - cos(θ)=1    → aligned with wind (boosts ignition)
  - cos(θ)=0    → perpendicular (neutral)
  - cos(θ)=-1   → against wind (reduces ignition)
```

**Ignition Formula (Spec 6.1):**

```
p_ign = clamp(0, 1, f(1-m)(1+α|w|cosθ) × ℓ_neighbor × (1+β(T-T_ref)))

Components:
1. f(1-m)                          → fuel-moisture factor
2. (1+α|w|cosθ)                    → wind component
3. ℓ_neighbor                      → neighbor fire intensity
4. (1+β(T-T_ref))                  → temperature component

Clamped to [0,1] as probability
```

**Key Methods:**

```python
# Initialize
fire_prop = FirePropagation(rng=rng, config=FirePropagationConfig())

# Calculate ignition probability
p = fire_prop.calculate_ignition_probability(
    target_sector=dormant_sector,
    neighbor_sector=burning_neighbor,
    wind=wind_state,
    from_row=5, from_col=5,
    to_row=4, to_col=5,
    global_temperature=25.0
)

# Stochastic ignition
if fire_prop.attempt_ignition(...):
    target_sector.state = SectorState.BURNING

# Fire dynamics
fire_level = fire_prop.update_fire_level(sector, sector_multiplier=1.0)
fuel = fire_prop.update_fuel(sector)
burn_level = fire_prop.update_burn_level(sector)

# Burnout/Extinguishment checks
if fire_prop.check_burnout(sector):
    sector.state = SectorState.ASH

if fire_prop.check_extinguishment(sector):
    sector.state = SectorState.ASH
```

**Configuration Tuning:**

```python
config = FirePropagationConfig(
    alpha_wind=0.01,                 # Wind influence strength
    beta_temperature=0.02,           # Temperature influence strength
    reference_temperature=20.0,      # Base temperature
    spread_rate=0.1,                 # Fire level growth per tick
    fuel_consumption_rate=0.05,      # Fuel consumed per fire level per tick
    extinguish_threshold=1.0,        # When sector becomes ASH
)
```

---

### 4. **SimulationEngine** (`src/engine/simulation_engine.py`)

**Purpose:** Main orchestrator implementing the 7-phase tick lifecycle with immutable state model.

**7-Phase Tick Lifecycle (Spec 4.1):**

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Snapshot currentState → previousState              │
│ (Immutable copy, no mutations after this)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: Fire Propagation                                   │
│ - Iterate burning sectors                                   │
│ - Attempt ignition of neighbors (4-neighborhood, Spec 5.3)  │
│ - Update fire_level, fuel, burn_level                       │
│ - Check burnout and extinguishment                          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: Agent Updates (TODO)                               │
│ - Fire brigades (extinguish)                                │
│ - Foresters (prevention)                                    │
│ Integrates with src/engine/agent_manager/                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 4: Environment Updates (TODO)                         │
│ - Wind dynamics (Perlin noise or similar)                   │
│ - Temperature evolution                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 5: Telemetry Generation (TODO)                        │
│ - Sector state changes                                      │
│ - Fire statistics                                           │
│ - Agent status                                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 6: RabbitMQ Publishing (TODO)                         │
│ - Publish telemetry to messaging system                     │
│ - Integrates with src/messaging/                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 7: Commit nextState                                   │
│ - current_snapshot = nextState                              │
│ - RNG state saved to snapshot                               │
│ - Logical time = tick * tick_interval                       │
└─────────────────────────────────────────────────────────────┘
```

**Logical Clock (Spec 2.1):**

```python
simulation_time = tick * tick_interval  # seconds

NOT: datetime.utcnow()  ← FORBIDDEN (breaks determinism)
```

**Immutable State Model:**
All state transitions follow: `previousSnapshot → computeNext → nextSnapshot`

No in-place mutations. Example:

```python
# CORRECT:
next_sectors = {sid: s.clone() for sid, s in previous.sectors.items()}
next_sectors[sector_id].fire_level = new_value

# WRONG:
previous.sectors[sector_id].fire_level = new_value  ← Mutates previous state!
```

**4-Neighborhood (Spec 5.3):**

```
        N
        ↑
        |
W ←─────*─────→ E
        |
        ↓
        S

Directions: [(-1,0), (0,1), (1,0), (0,-1)]
NO diagonals. Built with O(N) adjacency_map (not O(N²)).
```

**Key Methods:**

```python
# Initialize
engine = SimulationEngine(
    forest_map={sid: sector1, sid: sector2, ...},
    rng=RngManager(seed=42),
    fire_config=FirePropagationConfig(),
    simulation_id="sim-uuid",
    tick_interval=1.0  # 1 second per tick
)

# Initialize simulation
snapshot = engine.initialize(
    seed=42,
    initial_wind=Wind(speed=5.0, direction_degrees=90)
)

# Run single tick
snapshot = engine.step()
print(f"Tick {snapshot.tick}, time {snapshot.simulation_time}s")

# Access state
current_snapshot = engine.get_snapshot()
sector_state = engine.get_sector_state(sector_id)

# Manually ignite sector (e.g., from fire brigade)
engine.ignite_sector(sector_id)
```

**SimulationSnapshot Structure:**

```python
@dataclass
class SimulationSnapshot:
    simulation_id: str                   # UUID for tracing
    tick: int                            # Tick number (0, 1, 2, ...)
    simulation_time: float               # tick * tick_interval

    sectors: Dict[int, Sector]           # All sector states
    wind: Wind                           # Global wind
    global_temperature: float            # Global temperature
    rng_state: Dict[str, Any]           # RNG state for replay
    events: EventQueue                   # Audit trail of events
```

**Deterministic Replay:**

```python
# Save snapshot
snapshot_json = json.dumps(snapshot.to_dict())

# Later, restore and continue from exact state
snapshot = SimulationSnapshot.from_dict(json.loads(snapshot_json))
engine.current_snapshot = snapshot
engine.rng.set_state(snapshot.rng_state)

# Continue from exact point - identical results
next_snapshot = engine.step()
```

---

## Integration with Existing System

### REST API Integration (`main.py`)

The new engine replaces the simulation logic in `/run_simulation` endpoint:

```python
# OLD (to remove)
result = simple_simulation_engine.run(config)

# NEW
engine = SimulationEngine(
    forest_map=load_forest_from_config(config),
    rng=RngManager(seed=config.seed),
    fire_config=FirePropagationConfig(),
)

snapshot = engine.initialize(seed=config.seed)

for _ in range(config.num_ticks):
    snapshot = engine.step()

return snapshot.to_dict()
```

### Agent Manager Integration (`src/engine/agent_manager/`)

Fire brigades and foresters already implemented. Phase 3 will integrate:

```python
def _phase_agent_updates(self, next_sectors):
    """Phase 3: Agent updates."""

    # Fire brigades extinguish fire
    for brigade_action in fire_brigades.get_actions():
        sector_id = brigade_action.target_sector_id
        next_sectors[sector_id].extinguish_level += brigade_action.extinguish_amount

    # Foresters prevent ignition
    for forester_action in foresters.get_actions():
        sector_id = forester_action.target_sector_id
        next_sectors[sector_id].moisture += forester_action.moisture_increase

    return next_sectors
```

### RabbitMQ Messaging (`src/messaging/`)

Phase 6 will publish telemetry:

```python
def _phase_rabbitmq_publish(self, snapshot, telemetry):
    """Phase 6: Publish to RabbitMQ."""

    message = {
        "simulation_id": snapshot.simulation_id,
        "tick": snapshot.tick,
        "simulation_time": snapshot.simulation_time,
        "telemetry": telemetry,
    }

    publish_to_channel("fire.telemetry", message)
```

### Configuration (`forest_*.json`, `krakow_*.json`)

Load sector data:

```python
config = json.load(open("forest_5x5.json"))

sectors = {}
for sector_data in config["sectors"]:
    sector = Sector.from_dict(sector_data)
    sectors[sector.sector_id] = sector

engine = SimulationEngine(forest_map=sectors)
```

---

## Development Workflow

### 1. **Adding New Physics**

Example: Add wind dynamics to Phase 4:

```python
def _phase_environment_update(self, previous_snapshot):
    """Phase 4: Update environment."""

    # Example: Simple wind direction change
    old_wind = previous_snapshot.wind
    new_direction = (old_wind.direction_degrees + self.rng.uniform(-5, 5)) % 360
    new_wind = Wind(
        speed=old_wind.speed * 0.95 + self.rng.uniform(0, 0.5),
        direction_degrees=new_direction
    )

    new_temperature = previous_snapshot.global_temperature + self.rng.normal(0, 0.5)

    return new_wind, new_temperature
```

### 2. **Testing Determinism**

```python
def test_determinism():
    """Verify identical seed → identical results."""

    # Run 1
    engine1 = SimulationEngine(forest_map, rng=RngManager(seed=42))
    snapshot1 = engine1.initialize(seed=42)
    for _ in range(10):
        snapshot1 = engine1.step()

    # Run 2
    engine2 = SimulationEngine(forest_map, rng=RngManager(seed=42))
    snapshot2 = engine2.initialize(seed=42)
    for _ in range(10):
        snapshot2 = engine2.step()

    # Verify identical
    assert snapshot1.to_dict() == snapshot2.to_dict()
```

### 3. **Debugging Fire Spread**

Use event queue to trace what happened:

```python
snapshot = engine.step()

# Print all ignition events
for event in snapshot.events.get_events_by_type(EventType.IGNITION):
    print(f"Sector {event.sector_id} ignited at tick {event.tick}")

# Print all sector changes
for event in snapshot.events.get_events_for_sector(sector_id):
    print(f"Sector {sector_id}: {event.event_type.value}")
```

### 4. **Tuning Physics Parameters**

```python
config = FirePropagationConfig(
    alpha_wind=0.02,              # Increase wind effect
    beta_temperature=0.05,         # More temperature sensitivity
    spread_rate=0.15,              # Faster fire spread
    fuel_consumption_rate=0.08,    # Faster fuel depletion
)

engine = SimulationEngine(forest_map, fire_config=config)
```

---

## Common Pitfalls

| Pitfall                      | Problem                 | Solution                                        |
| ---------------------------- | ----------------------- | ----------------------------------------------- | --- | --- | --- | --------------------- |
| Using `random.random()`      | Breaks determinism      | Use `rng.random()`                              |
| Using `datetime.utcnow()`    | Non-deterministic time  | Use `tick * tick_interval`                      |
| Mutating `previous_snapshot` | Immutability violated   | Clone first: `next_sectors = {...s.clone()...}` |
| Direct state assignment      | Bypasses FSM            | Check `is_flammable()` before burning           |
| Nested RNG initialization    | Seed conflicts          | Use single `RngManager` instance                |
| Ignoring extinguish_level    | Missing brigade effects | Update in phase 3, check in phase 2             |
| Wind coefficient tuning      | Unrealistic physics     | Keep                                            | α   | w   |     | reasonable [0.1, 0.5] |

---

## Performance Notes

| Operation           | Complexity | Notes                              |
| ------------------- | ---------- | ---------------------------------- |
| Build adjacency map | O(N)       | Uses position_map for O(1) lookup  |
| Single tick         | O(B × N)   | B=burning sectors, N=avg neighbors |
| Snapshot clone      | O(S)       | S=total sectors                    |
| RNG call            | O(1)       | NumPy RandomState                  |

For 25×25 map (625 sectors):

- Adjacency build: ~2500 ops
- Tick (worst case): ~40k ops
- Snapshot clone: ~50k ops

---

## Files Checklist

- ✅ `src/engine/rng_manager.py` - Deterministic RNG
- ✅ `src/engine/models/sector.py` - Domain entity (4 states)
- ✅ `src/engine/models/fire_propagation.py` - Physics engine
- ✅ `src/engine/simulation_engine.py` - 7-phase engine
- ✅ `src/engine/models/event_queue.py` - Event audit trail
- 🔄 `main.py` - REST API integration (in progress)
- 🔄 Phase 3: Agent manager integration (in progress)
- 🔄 Phase 4: Environment dynamics (in progress)
- 🔄 Phase 5: Telemetry generation (in progress)
- 🔄 Phase 6: RabbitMQ publishing (in progress)

---

## Questions?

Refer to spec: [README_FSS.md](../../README_FSS.md)

For issues, create event trace and share `snapshot.events` output.
