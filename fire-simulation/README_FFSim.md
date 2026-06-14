# FFSim Fire Propagation Engine - Developer Guide

## Overview

This document describes the current FFSim fire propagation engine used by `fire-simulation`. The code centers around deterministic snapshots, the `RngManager`, the `Sector` model, the `FirePropagation` physics engine, the `EventQueue` audit trail, the `AgentManager` for firefighting coordination, the `SimulationEngine` 7-phase lifecycle orchestrator with Flask REST API, SensorArray, and RabbitMQ telemetry publishing, and the `ExperimentLogger` for per-tick JSONL experiment logging.

**Key architecture principles:**

- **Determinism:** identical seed + config + command order => identical simulation
- **Immutable tick model:** `current_snapshot -> next_snapshot`, with cloned sectors per tick
- **Single RNG source:** all randomness flows through `RngManager`
- **Event audit trail:** all state changes recorded in `EventQueue` for replay
- **Agent coordination:** fire brigades and foresters managed by `AgentManager`
- **7-phase lifecycle:** `Snapshot → Propagation → Agents → Environment → Telemetry → Messaging → Commit`
- **Sensor telemetry:** SensorArray with deterministic noise generation per sector configuration (spec 5.2.2)
- **Messaging:** RabbitMQ Blocking Connection publisher for spec 5.2 routing keys (sectors, sensors, agents)
- **REST API:** Flask app (`main_new.py`) with background tick loop for testing and integration
- **Experiment logging:** optional per-tick JSONL output with latency metrics, activated via `experimentLog` field in `/run_simulation`

---

## Module architecture

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

### 2. `Sector` (`src/engine/models/sector.py`)

**Purpose:** domain entity representing a single forest sector.

**Current sector states:**

- `DORMANT` – sector is not burning yet
- `BURNING` – sector is currently burning
- `EXTINGUISHED` – sector was suppressed by firefighting
- `ASH` – sector is burnt out / permanently consumed

**State transitions:**

```text
DORMANT -> BURNING        ignition
BURNING -> ASH            burnout or extinguishment
BURNING -> EXTINGUISHED   extinguishment path
EXTINGUISHED -> ASH       final terminal state in the engine flow
```

**Sector fields:**

- `moisture: [0, 1]` – reduces ignition probability
- `fuel: [0, 1]` – consumed during burning
- `fire_level: [0, 1]` – current intensity
- `burn_level: [0, 1]` – cumulative burn amount
- `extinguish_level: [0, 1]` – suppression progress
- `temperature: float` – current sector-local temperature
- `sector_type: SectorType`

**Current `SectorType` values:**

- `DECIDUOUS`
- `CONIFEROUS`
- `MIXED`
- `FIELD`
- `FALLOW`
- `WATER`
- `UNTRACKED`

**Current methods:**

```python
sector.is_flammable()
sector.is_burning()
sector.clone()
sector.to_dict()
sector.from_dict(data)
sector.get_fire_classification()
sector.get_fire_state_name()
```

**Validation:**

- `moisture`, `fuel`, `fire_level`, `burn_level`, `extinguish_level` are validated in `__post_init__()`
- temperature is not clamped

**Flammability coefficients used by the engine:**

```python
coefficients = {
    SectorType.FIELD: 1.5,
    SectorType.FALLOW: 1.2,
    SectorType.CONIFEROUS: 1.2,
    SectorType.MIXED: 1.0,
    SectorType.DECIDUOUS: 0.8,
    SectorType.WATER: 0.0,
    SectorType.UNTRACKED: 1.0,
}
```

**Fire classification (section 5.4 – Klimek ISD2024 Table 1):**

Sectors are classified into 6 discrete levels based on `fire_level` for telemetry and resource planning:

| Level | Name                     | Resources          | Fuel Rate       |
| ----- | ------------------------ | ------------------ | --------------- |
| 0     | NON_COMBUSTED            | –                  | –               |
| 1     | EARLY_FIRE               | one fire engine    | 0.5×            |
| 2     | MEDIUM_FIRE              | local fire station | 1.0× (baseline) |
| 3     | FULL_FIRE                | maximum crews      | 2.0×            |
| 4     | EXTREME_FIRE             | exceeds local      | 4.0×            |
| 5     | COMBUSTED / EXTINGUISHED | –                  | –               |

**Mapping from continuous `fire_level` [0,1] to classification:**

```python
if state in (ASH, EXTINGUISHED):
    return 5  # Terminal
if state != BURNING:
    return 0  # Not burning
if fire_level <= 0.0:
    return 0
if fire_level <= 0.25:
    return 1  # EARLY_FIRE
if fire_level <= 0.50:
    return 2  # MEDIUM_FIRE
if fire_level <= 0.75:
    return 3  # FULL_FIRE
return 4      # EXTREME_FIRE
```

**New sector methods:**

```python
classification = sector.get_fire_classification()      # Returns 0-5
fire_state = sector.get_fire_state_name()              # Returns string
coeff = sector.get_flammability_coefficient()           # Returns float
```

---

### 3. `FirePropagation` (`src/engine/models/fire_propagation.py`)

**Purpose:** physics engine for ignition, fire growth, fuel consumption and extinguishment checks.

**Wind model (spec section 2.4.1):**

```text
wind_component = 1 + α · |w| · cosθ
```

where:

- `|w|` = wind speed in km/h (NOT normalized per spec)
- `cosθ` = cosine of angle between wind direction and spread direction
- `α` = configurable wind influence coefficient (default 0.01)
- Wind direction: 0° = North, 90° = East, 180° = South, 270° = West

**Ignition formula (spec section 6.1, rule R1):**

Canonical formula:

```text
p_ign = clamp(0, 1,
    f · (1 − m)
    · (1 + α · |w| · cosθ)
    · ℓ_neighbor
    · max(0, 1 + β · (T − T_ref))
)
```

Where:

- `f` = target sector fuel [0,1]
- `m` = target sector moisture [0,1]
- `|w|` = wind speed in km/h (raw, not normalized)
- `cosθ` = angle factor between wind and spread direction
- `ℓ_neighbor` = neighbor burning sector's fire_level
- `T` = global temperature (°C)
- `T_ref` = reference temperature (default 20°C)
- `α`, `β` = tunable coefficients

**Current methods:**

```python
fire_prop = FirePropagation(rng=rng, config=FirePropagationConfig())

p = fire_prop.calculate_ignition_probability(
    target_sector=dormant_sector,
    neighbor_sector=burning_neighbor,
    wind=wind_state,
    from_row=5,
    from_col=5,
    to_row=4,
    to_col=5,
    global_temperature=25.0,
)

ignites = fire_prop.attempt_ignition(
    target_sector=dormant_sector,
    neighbor_sector=burning_neighbor,
    wind=wind_state,
    from_row=5,
    from_col=5,
    to_row=4,
    to_col=5,
    global_temperature=25.0,
)

new_fire_level = fire_prop.update_fire_level(sector, sector_multiplier=1.0)
new_fuel = fire_prop.update_fuel(sector)
new_burn_level = fire_prop.update_burn_level(sector)

if fire_prop.check_burnout(sector):
    sector.state = SectorState.ASH

if fire_prop.check_extinguishment(sector):
    sector.state = SectorState.ASH
```

**Configuration defaults:**

```python
FirePropagationConfig(
    alpha_wind=0.01              # wind influence coefficient
    beta_temperature=0.02        # temperature coefficient
    reference_temperature=20.0   # °C
    ignition_base=0.10           # initial fire_level of ignited sector
    spread_rate=0.1              # base spread per tick
    wind_multiplier_max=2.0      # max wind effect
    fuel_consumption_rate=0.02   # base consumption per tick
    extinguish_threshold=1.0     # when sector is extinguished
    fuel_consumption_multiplier = {
        1: 0.5,   # EARLY_FIRE   — 1 engine
        2: 1.0,   # MEDIUM_FIRE  — baseline
        3: 2.0,   # FULL_FIRE    — max crews
        4: 4.0,   # EXTREME_FIRE — exceeds capacity
    }
)
```

**Fuel consumption rates (per fire classification):**

Rate per tick = `fuel_consumption_rate × multiplier[fire_class]`

- Class 1 (EARLY_FIRE) → 0.5× rate
- Class 2 (MEDIUM_FIRE) → 1.0× rate (baseline)
- Class 3 (FULL_FIRE) → 2.0× rate
- Class 4 (EXTREME_FIRE) → 4.0× rate

**Neighborhood:** fire spread is evaluated on the 4-neighborhood (`North`, `East`, `South`, `West`).

---

### 4. `SimulationEngine` (`src/engine/simulation_engine.py`)

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
│ Phase 3: Agent Updates                                      │
│ - Fire brigades: apply extinguishing (extinguish_level++)  │
│ - Foresters: patrol mode (prevention via moisture++)       │
│ - Auto-withdraw foresters from burning sectors              │
│ - Travel time countdowns                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 4: Environment Updates (partial)                      │
│ - Wind: currently passed through (TODO: wind walk)          │
│ - Temperature: currently passed through (TODO: evolution)   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 5: Telemetry Generation                               │
│ - Collect sector states and changes                         │
│ - Read all sensors via SensorArray (deterministic noise)    │
│ - Compile agent telemetry (brigades, foresters)             │
│ - Returns telemetry dict for Phase 6                        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 6: RabbitMQ Publication                               │
│ - Publish sector states via spec 5.2.1 routing keys         │
│ - Publish sensor readings via spec 5.2.2 routing keys       │
│ - Publish agent states via spec 5.2.3 routing keys          │
│ - Graceful fallback if RabbitMQ unavailable                 │
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

## Practical Notes

### Reproducibility

To reproduce a run, persist and restore:

- `seed` — random number generator seed
- `initial sectors` — all sector properties (fuel, moisture, etc.)
- `initial wind` — speed and direction
- `initial temperature` — global temperature
- `tick order` — commands must execute in same order
- `agent orders` — commands from support system (if any)

**Proof:** `simulation_id + seed + tick order => identical snapshots`

### Testing & Verification

**Unit test pattern:**

```python
from src.engine.simulation_engine import SimulationEngine
from src.engine.rng_manager import RngManager
from src.engine.models.sector import Sector, SectorType

# Create test forest
sectors = {
    0: Sector(sector_id=0, row=0, column=0,
              sector_type=SectorType.FOREST, fuel=1.0, moisture=0.3),
}

# Create deterministic engine
rng = RngManager(seed=12345)
engine = SimulationEngine(forest_map=sectors, rng=rng)
snapshot = engine.initialize(seed=12345)

# Tick
next_snap = engine.step()
assert next_snap.tick == 1
```

**Integration test pattern:**

```bash
# Start server
python3 main_new.py &

# Run simulation
curl -X POST http://localhost:5000/run_simulation -d '...'

# Poll snapshots
curl http://localhost:5000/snapshot | jq '.tick'

# Stop
curl -X POST http://localhost:5000/stop_simulation
```

### Event Replay

Because all events are recorded in `EventQueue`, you can audit what happened each tick:

```python
snapshot = engine.get_snapshot()
ignitions = snapshot.events.get_ignition_events()
for event in ignitions:
    print(f"Sector {event.sector_id} ignited: "
          f"{event.old_value} → {event.new_value}")
```

### Current Limitations

- Environment dynamics are **stub** (wind and temperature passed through unchanged)
- RabbitMQ integration not yet connected
- LLM support system not integrated
- Forester patrol suppression effect (moisture increase) not yet implemented
- UI/visualization not included in `main_new.py`

### Performance Notes

- **O(N) adjacency** for 4-neighborhood (not O(N²))
- **RNG state** includes full numpy RandomState (large when serialized)
- **EventQueue** grows per tick; periodic cleanup recommended in production

---

---

## 5. `EventQueue` (`src/engine/models/event_queue.py`)

**Purpose:** Deterministic audit trail of all simulation state changes for replay and debugging.

**Event types:**

```python
class EventType(Enum):
    IGNITION = "IGNITION"                 # Sector caught fire
    BURNOUT = "BURNOUT"                   # Fuel depleted
    EXTINGUISHMENT = "EXTINGUISHMENT"     # Suppressed
    FUEL_UPDATE = "FUEL_UPDATE"           # Fuel consumed
    BURN_LEVEL_UPDATE = "BURN_LEVEL_UPDATE"
    FIRE_LEVEL_UPDATE = "FIRE_LEVEL_UPDATE"
```

**Key methods:**

```python
events = EventQueue()

# Record events during tick
events.add_event(tick=5, event_type=EventType.IGNITION,
                 sector_id=42, old_value=0.0, new_value=0.1)

# Query events
ignitions = events.get_ignition_events()
burnouts = events.get_burnout_events()
sector_events = events.get_events_for_sector(sector_id=42)

# Snapshot
snapshot.events = events
events_dict = events.to_dict()  # {event_count, events: [...]}
```

**Usage in snapshot:**

```python
# Every tick creates an immutable EventQueue in the snapshot
snapshot.events.get_events_by_type(EventType.IGNITION)  # All ignitions this tick
```

---

## 6. `SimulationSnapshot` — Enhanced (`src/engine/simulation_engine.py`)

**Purpose:** Complete immutable state capture at each tick for determinism and debugging.

**New fields:**

```python
@dataclass
class SimulationSnapshot:
    simulation_id: str
    tick: int
    simulation_time: float      # tick * tick_interval (seconds)
    sectors: Dict[int, Sector]  # All sector states
    wind: Wind
    global_temperature: float
    rng_state: Dict[str, Any]   # {seed, call_count, rng_state}
    events: EventQueue          # Audit trail (NEW)
    agents: Dict[str, Any]      # Agent states (NEW)
```

**New method:**

```python
snapshot_dict = snapshot.to_dict()  # JSON-serializable dict
# Contains rng_state with seed/call_count (not numpy internals)
# Contains all sector, wind, agent, and event data
```

---

## 7. `AgentManager` (`src/engine/agent_manager.py`)

**Purpose:** Manage fire brigades and forester patrols with coordinated dispatching and state tracking.

**Agent states:**

```python
class AgentState(Enum):
    AVAILABLE     = "AVAILABLE"
    TRAVELLING    = "TRAVELLING"
    PATROLLING    = "PATROLLING"      # Foresters only
    EXTINGUISHING = "EXTINGUISHING"   # Fire brigades only
```

**Agent types:**

- **ForesterPatrol**: `AVAILABLE → TRAVELLING → PATROLLING → AVAILABLE`
  - Preventive action: increases sector moisture
  - Travel time: configurable (default 5 ticks)
- **FireBrigade**: `AVAILABLE → TRAVELLING → EXTINGUISHING → AVAILABLE`
  - Combat action: increases sector extinguish_level
  - Rate: `extinguish_rate` per tick (default 0.05)

**Configuration:**

```python
@dataclass
class AgentConfig:
    travel_time: int = 5           # Ticks to reach target
    extinguish_rate: float = 0.05  # extinguish_level increase per tick
```

**Key methods:**

```python
manager = AgentManager()

# Register agents from config
manager.register_forester(forester_id=1, base_location=Location(lon=10, lat=20))
manager.register_brigade(brigade_id=101, base_location=Location(lon=15, lat=25))

# Phase 2 of tick: process all agent states
events = manager.process_tick(
    next_sectors=next_sectors,
    previous_sectors=previous_sectors,
    current_tick=tick_count
)

# Apply orders from support system
result = manager.apply_forester_order(order_dict, sectors)
result = manager.apply_brigade_order(order_dict, sectors)
result = manager.apply_assign_brigades(order_dict, sectors)

# Snapshot support
agents_copy = manager.clone()
agents_dict = manager.to_dict()
```

**Agent events:**

```python
class AgentEventType(Enum):
    FORESTER_DISPATCHED
    FORESTER_ARRIVED
    FORESTER_RETURNED
    FORESTER_AUTO_WITHDRAWN    # Auto-withdraw from burning sectors
    BRIGADE_DISPATCHED
    BRIGADE_ARRIVED
    BRIGADE_RETURNED
```

**Special rule — auto-withdraw:**

When a forester's current sector becomes `BURNING`, they are automatically withdrawn with an `FORESTER_AUTO_WITHDRAWN` event.

---

## 8. Flask REST API (`main_new.py`)

**Purpose:** Minimal Flask app exposing simulation control without RabbitMQ or Backend dependencies.

**Endpoints:**

| Endpoint             | Method | Purpose                              |
| -------------------- | ------ | ------------------------------------ |
| `/run_simulation`    | POST   | Start simulation with config         |
| `/stop_simulation`   | POST   | Stop background loop                 |
| `/step`              | POST   | Manual tick(s) (when not running)    |
| `/snapshot`          | GET    | Get current state                    |
| `/health`            | GET    | Health check                         |
| `/set_speed`         | POST   | Set `tickInterval` (seconds/tick)    |
| `/orderFireBrigade`  | POST   | Dispatch brigade (spec 5.1)          |
| `/orderForestPatrol` | POST   | Dispatch forester (spec 5.1)         |
| `/assignBrigades`    | POST   | Assign brigades to sector (spec 5.1) |

**Run:**

```bash
RABBITMQ_HOST=localhost python3 main_new.py
# Runs on http://0.0.0.0:5000
```

**Example — start simulation:**

```bash
curl -X POST http://localhost:5000/run_simulation \
  -H "Content-Type: application/json" \
  -d '{
    "seed": 42,
    "tick_interval": 1.0,
    "mapConfig": {
      "rows": 10,
      "columns": 10,
      "sectors": [{
        "sectorId": 0,
        "row": 0,
        "column": 0,
        "sectorType": "FOREST",
        "fuel": 1.0,
        "moisture": 0.3
      }],
      "fireBrigades": [{
        "fireBrigadeId": 1,
        "baseLocation": {"longitude": 5.0, "latitude": 5.0}
      }],
      "foresterPatrols": [{
        "foresterPatrolId": 1,
        "baseLocation": {"longitude": 0.0, "latitude": 0.0}
      }],
      "ignite": [50]
    }
  }'
```

**Example — get snapshot:**

```bash
curl http://localhost:5000/snapshot | jq .
# Returns: {simulation_id, tick, sectors, wind, temperature, agents, events, ...}
```

**Multithreading:**

- `EngineHost._run_loop()` runs in background thread
- Each tick sleeps `tickInterval` seconds
- Lock protects concurrent access to engine
- Manual `/step` disabled when loop is running

---

## 9. RabbitMQ Publisher (`src/messaging/rabbitmq_publisher.py`)

**Purpose:** Blocking connection RabbitMQ publisher implementing spec section 5.2 telemetry routing.

**Architecture:**

Uses `pika.BlockingConnection` for synchronous, deterministic 1-tick/sec simulation:

- Single channel per publisher
- Topic exchange "fire_updates" (durable)
- Persistent delivery mode (survives RabbitMQ restart)
- Graceful fallback if RabbitMQ unavailable (`publisher.available = False`)
- Connection retry policy: 3 attempts, 1-second delay

**Routing Keys (Spec 5.2):**

```
Sector State (5.2.1):
  simulation.telemetry.map.sector_state             # Full state
  simulation.telemetry.map.sector_state_fast        # Changed sectors only

Sensor Readings (5.2.2):
  simulation.telemetry.sensors.WIND_SPEED           # Per sensor type
  simulation.telemetry.sensors.TEMP_HUMIDITY
  simulation.telemetry.sensors.LITTER_MOISTURE
  simulation.telemetry.sensors.CO2
  simulation.telemetry.sensors.PM2_5
  simulation.telemetry.sensors.CAMERA

Agent States (5.2.3):
  simulation.telemetry.agents.fire_brigade.*        # Brigade telemetry
  simulation.telemetry.agents.forester.*            # Forester telemetry
  simulation.telemetry.agents.fire_brigade_batch    # Batch variant
  simulation.telemetry.agents.forester_batch        # Batch variant
```

**Key Methods:**

```python
publisher = RabbitMQPublisher(host="localhost", port=5672)

# Direct publishing
publisher.publish(routing_key="simulation.telemetry.map.sector_state",
                  message={"sectorId": 1, "fireLevel": 0.5})

# Sector state (spec 5.2.1)
publisher.publish_sector_state({"sectorId": 1, "fireLevel": 0.5})
publisher.publish_sector_state_fast(changed_sectors)

# Sensor readings (spec 5.2.2)
publisher.publish_sensor_reading(sensor_type="WIND_SPEED",
                                 sensor_id=1,
                                 location={"lon": 10.0, "lat": 20.0},
                                 data={"value": 5.0, "noise": 0.2},
                                 timestamp="2024-01-01T12:00:00Z")

# Agent states (spec 5.2.3)
publisher.publish_fire_brigade_state(brigade_id=1, state="EXTINGUISHING", ...)
publisher.publish_forester_state(forester_id=1, state="PATROLLING", ...)

# Batch variants
publisher.publish_fire_brigade_batch([brigade1_telemetry, brigade2_telemetry])
publisher.publish_forester_batch([forester1_telemetry, forester2_telemetry])

# Check availability
if publisher.available:
    # Can safely call publish methods
    pass
```

**JSON Format (Examples):**

Sector State:

```json
{
  "sectorId": 1,
  "fireLevel": 0.7,
  "burnLevel": 0.5,
  "extinguishLevel": 0.2,
  "fireState": "BURNING"
}
```

Sensor Reading:

```json
{
  "sensorId": 100,
  "sensorType": "WIND_SPEED",
  "location": { "lon": 10.0, "lat": 20.0 },
  "data": { "value": 5.0, "noise": 0.2 },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

Brigade State:

```json
{
  "fireBrigadeId": 1,
  "state": "EXTINGUISHING",
  "location": { "lon": 10.0, "lat": 20.0 },
  "sectorId": 50,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

---

## 10. Sensor Array (`src/engine/sensors.py`)

**Purpose:** Deterministic sensor array generating realistic readings per sector configuration (spec 5.2.2).

**Architecture:**

All noise generated via `RngManager` for 100% reproducibility. Supports 7 sensor types:

- WIND_SPEED, WIND_DIRECTION
- TEMP_HUMIDITY (temperature + humidity)
- LITTER_MOISTURE
- CO2, PM2_5
- CAMERA (smoke detection)

**Sensor Configurations:**

```python
# Per-sector sensor setup via mapConfig.sensors:
{
  "sensors": {
    "WIND_SPEED": [1, 2, 5, 10],           # Sensor in sectors 1, 2, 5, 10
    "TEMP_HUMIDITY": [1, 3, 5, 7],
    "LITTER_MOISTURE": [2, 4, 6, 8],
    "CO2": [all_sectors],
    "PM2_5": [burning_sectors],
    "CAMERA": [high_risk_sectors]
  }
}
```

**Noise Models (Per Sensor Type):**

```
WIND_SPEED:      ±5% of reading
WIND_DIRECTION:  ±10° noise
TEMP_HUMIDITY:   ±3°C temperature, ±10% relative humidity
LITTER_MOISTURE: ±0.05 variation
CO2:             ±50 ppm noise
PM2_5:           ±15% variation
CAMERA:          10% baseline smoke detection (deterministic from RNG)
```

**Key Methods:**

```python
sensor_array = SensorArray(rng=rng_manager)

# Add sensor to sector
config = SensorConfig(
    sector_id=1,
    sensor_id=100,  # Base ID scheme: sector_id * 100
    enabled_types=[SensorType.WIND_SPEED, SensorType.TEMP_HUMIDITY],
    location={"lon": 10.0, "lat": 20.0}
)
sensor_array.add_sensor(config)

# Read all sensors for current tick
readings = sensor_array.read_all(
    timestamp="2024-01-01T12:00:00Z",
    wind_speed=5.0,
    wind_direction=45.0,
    global_temperature=22.0
)

# Read sensors by sector
sector_readings = sensor_array.read_by_sector(
    sector_id=1,
    timestamp="2024-01-01T12:00:00Z",
    wind_speed=5.0,
    wind_direction=45.0,
    global_temperature=22.0
)
```

**Example Sensor Reading (Dataclass):**

```python
@dataclass
class SensorReading:
    sensor_id: int           # 100 (sector 1's WIND_SPEED sensor)
    sensor_type: SensorType  # WIND_SPEED
    location: Dict           # {"lon": 10.0, "lat": 20.0}
    data: Dict               # Type-specific (e.g., {"value": 4.75, "noise": 0.25})
    timestamp: str           # "2024-01-01T12:00:00Z"

    def to_dict(self) -> Dict[str, Any]:
        # Returns JSON-serializable dict for RabbitMQ publishing
```

**Integration in SimulationEngine (Phase 5):**

```python
def _phase_telemetry_generation(self, next_sectors, ...) -> Dict:
    """Phase 5: Collect sector states + sensor readings + agent states."""

    # Sector state telemetry (spec 5.2.1)
    for sector_id, sector in next_sectors.items():
        telemetry["sectors"].append({
            "sectorId": sector_id,
            "fireLevel": sector.fire_level,
            ...
        })

    # Sensor readings (spec 5.2.2) — deterministic via RNG
    sensor_readings = self.sensor_array.read_all(
        timestamp=timestamp,
        wind_speed=wind.speed,
        wind_direction=wind.direction_degrees,
        global_temperature=temperature
    )
    for reading in sensor_readings:
        telemetry["sensors"].append(reading.to_dict())

    # Agent telemetry (spec 5.2.3)
    agents_dict = self.agent_manager.to_dict()
    # ... process brigades and foresters

    return telemetry
```

---

## 11. Experiment Logger (`experiment_logger.py`)

**Purpose:** Per-tick JSONL logging of simulation metrics for experiment analysis and regression testing (spec section 9).

**Activated by** passing `experimentLog` in the `/run_simulation` request body. Omitting the field disables logging entirely — zero overhead in production.

**Two classes:**

- `ExperimentLogger` — writes one JSON record per tick to a JSONL file (thread-safe)
- `SimulationMetricsTracker` — accumulates latency data across the full simulation run; held by `EngineHost` and updated from the engine and REST handlers

### Output format

Each line of the JSONL file is a standalone JSON object (spec section 9):

```jsonl
{"tick": 0, "burning": 1, "burnt": 0, "detectionLatency": null, "responseLatency": null, "activeAgents": 0, "ordersReceived": []}
{"tick": 5, "burning": 4, "burnt": 0, "detectionLatency": 3.0, "responseLatency": null, "activeAgents": 2, "ordersReceived": ["EXTINGUISH:14"]}
{"tick": 10, "burning": 2, "burnt": 3, "detectionLatency": 3.0, "responseLatency": 5.0, "activeAgents": 2, "ordersReceived": []}
```

**Field definitions (spec section 9):**

| Field              | Type          | Description                                                                                         |
| ------------------ | ------------- | --------------------------------------------------------------------------------------------------- |
| `tick`             | int           | Current tick number (from 0)                                                                        |
| `burning`          | int           | Sectors in `BURNING` state                                                                          |
| `burnt`            | int           | Sectors in `ASH` or `EXTINGUISHED` state                                                            |
| `detectionLatency` | float \| null | Avg ticks from first ignition to first support order for each fire; `null` if no orders yet         |
| `responseLatency`  | float \| null | Avg ticks from EXTINGUISH order to brigade arriving at sector; `null` if no brigade has arrived yet |
| `activeAgents`     | int           | Agents not in `AVAILABLE` state (foresters + brigades in travel or action)                          |
| `ordersReceived`   | list[str]     | Orders received this tick, format `"ACTION:sectorId"` (e.g. `"EXTINGUISH:14"`)                      |

### Latency tracking

**`detectionLatency`** is computed over all ignited sectors for which a support order has been issued:

```
detectionLatency = avg(first_order_tick[sector] - ignition_tick[sector])
```

**`responseLatency`** is computed over all brigades that have completed travel:

```
responseLatency = avg(arrive_tick[brigade] - dispatch_tick[brigade])
```

Both metrics are cumulative averages — they include all fires/brigades across the entire run, not just the current tick.

### Key methods

```python
from experiment_logger import ExperimentLogger, SimulationMetricsTracker

# --- ExperimentLogger ---
logger = ExperimentLogger(path="/tmp/run1.jsonl")

logger.record_tick(
    tick=47,
    sectors=snapshot.sectors,
    agent_manager=agent_manager,
    orders_this_tick=["EXTINGUISH:14", "PATROL:2"],
    ignition_tick_map={14: 44},        # sector_id → tick of ignition
    first_order_tick_map={14: 47},     # sector_id → tick of first order
    brigade_dispatch_map={1: 47},      # brigade_id → tick dispatched
    brigade_arrive_map={1: 52},        # brigade_id → tick arrived
)

logger.close()

# --- SimulationMetricsTracker ---
tracker = SimulationMetricsTracker()

# Call from engine during fire propagation phase:
tracker.on_ignition(sector_id=14, tick=44)

# Call from REST handler after successful order:
tracker.on_order_received(sector_id=14, tick=47, order_str="EXTINGUISH:14")
tracker.on_brigade_dispatched(brigade_id=1, tick=47)

# Call from engine after processing AgentEvents:
tracker.on_brigade_arrived(brigade_id=1, tick=52)

# Pass to logger each tick:
logger.record_tick(
    tick=snap.tick,
    sectors=snap.sectors,
    agent_manager=agent_manager,
    orders_this_tick=tracker.flush_orders(),   # resets the list
    **tracker.snapshot_for_logger(),           # passes all maps
)
```

### Activation via REST API

```bash
curl -X POST http://localhost:5000/run_simulation \
  -H "Content-Type: application/json" \
  -d '{
    "seed": 42,
    "experimentLog": "/tmp/experiment_run1.jsonl",
    "mapConfig": {
      "rows": 10,
      "columns": 10,
      "wind": {"speed": 15.0, "direction_degrees": 90},
      "ignite": [55]
    }
  }'
```

The log file is flushed and closed automatically when `/stop_simulation` is called or the engine exits.

### Integration points in existing code

See `logger_integration_patch.py` for the exact diff. In summary:

1. **`main_new.py` `EngineHost.start()`** — create `ExperimentLogger` and `SimulationMetricsTracker` when `experimentLog` key is present; attach tracker to engine.
2. **`main_new.py` `EngineHost._run_loop()`** — call `logger.record_tick()` after `engine.step()`.
3. **`main_new.py` `EngineHost.stop()`** — call `logger.close()`.
4. **`main_new.py` REST handlers** — call `tracker.on_order_received()` and `tracker.on_brigade_dispatched()` after successful validation.
5. **`simulation_engine.py` `_phase_fire_propagation()`** — call `tracker.on_ignition()` when a sector transitions to `BURNING`.
6. **`simulation_engine.py` `step()`** — scan `self.last_events` for `BRIGADE_ARRIVED` events and call `tracker.on_brigade_arrived()`.

---

## Current Status & TODOs

### ✅ Implemented

- ✅ Deterministic fire propagation engine with 4-neighborhood
- ✅ RNG manager with state snapshots
- ✅ Fire classification system (0–5 levels)
- ✅ Fuel consumption multipliers per class
- ✅ EventQueue for audit trails
- ✅ Agent manager with ForesterPatrol and FireBrigade
- ✅ Auto-withdraw of foresters from burning sectors
- ✅ REST API for simulation control
- ✅ Flask multithreading with background tick loop
- ✅ SimulationSnapshot serialization to JSON
- ✅ RabbitMQ Publisher (Blocking Connection, graceful fallback)
- ✅ SensorArray with 7 sensor types and deterministic noise
- ✅ Telemetry generation (Phase 5) and publishing (Phase 6)
- ✅ Integration in SimulationEngine.step()

### 🔲 TODO

- [ ] Wind walk dynamics (Phase 4, currently passed through)
- [ ] Temperature evolution (Phase 4, currently static)
- [ ] LLM support system integration
- [ ] Agent order persistence across ticks
- [ ] Forester moisture increase effect
- [ ] UI/visualization endpoints
- [ ] Database persistence for simulation runs

---

## Files worth checking

- `src/engine/rng_manager.py` — Deterministic RNG
- `src/engine/models/sector.py` — Sector entity with fire classification
- `src/engine/models/fire_propagation.py` — Wind model (NOT normalized) and ignition physics
- `src/engine/models/event_queue.py` — Event audit trail
- `src/engine/simulation_engine.py` — Main orchestrator with 7-phase lifecycle (including telemetry)
- `src/engine/agent_manager.py` — Agent dispatch and state management
- `src/engine/sensors.py` — SensorArray with deterministic noise models
- `src/messaging/rabbitmq_publisher.py` — RabbitMQ Blocking Connection publisher
- `main_new.py` — Flask REST API and multithreaded engine host with sensor configuration
