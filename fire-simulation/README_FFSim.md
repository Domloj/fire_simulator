# FFSim Fire Propagation Engine - Developer Guide

## Overview

This document describes the current FFSim fire propagation engine used by `fire-simulation`. The code now centers around deterministic snapshots, the `RngManager`, the `Sector` model and the `FirePropagation`/`SimulationEngine` pipeline.

**Key architecture principles:**

- **Determinism:** identical seed + config + command order => identical simulation
- **Immutable tick model:** `current_snapshot -> next_snapshot`, with cloned sectors per tick
- **Single RNG source:** all randomness flows through `RngManager`
- **7-phase lifecycle:** `Snapshot -> Propagation -> Agent Updates -> Environment -> Telemetry -> RabbitMQ -> Commit`

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

---

### 3. `FirePropagation` (`src/engine/models/fire_propagation.py`)

**Purpose:** physics engine for ignition, fire growth, fuel consumption and extinguishment checks.

**Wind model:**

```text
wind_component = 1 + α · ‖w‖_norm · cosθ
```

where:

- `‖w‖_norm = speed / max_wind`, clamped to `[0, 1]`
- `cosθ` depends on angle between wind direction and the target spread direction
- `α` is the configurable wind coefficient

**Ignition formula:**

```text
p_ign = clamp(0, 1,
    fuel · (1 - moisture)
    · (1 + α · ‖w‖_norm · cosθ)
    · neighbor_fire_level
    · max(0, 1 + β · (T - T_ref))
)
```

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

**Current config defaults:**

```python
FirePropagationConfig(
    alpha_wind=0.3,
    beta_temperature=0.02,
    max_wind=80.0,
    reference_temperature=20.0,
    ignition_base=0.15,
    spread_rate=0.1,
    wind_multiplier_max=2.0,
    fuel_consumption_rate=0.02,
    extinguish_threshold=1.0,
)
```

**Fuel consumption:**

- fire class `1` -> multiplier `0.5`
- fire class `2` -> multiplier `1.0`
- fire class `3` -> multiplier `2.0`
- fire class `4` -> multiplier `4.0`

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

## Practical notes

### Reproducibility

To reproduce a run, persist:

- seed
- initial sectors
- initial wind
- initial temperature
- tick order / command sequence

### Current limitations

- agent, telemetry, and RabbitMQ phases are still placeholders in `SimulationEngine`
- environment dynamics are currently unchanged (`wind` and `temperature` are passed through)
- `sector.py` and `fire_propagation.py` were updated independently, so always validate the exact code in those files before using examples from older documentation

### Minimal smoke test

```python
rng = RngManager(seed=42)
engine = SimulationEngine(seed=42, tick_interval=60)

snapshot = engine.initialize(initial_sectors, wind, 25.0)
next_snapshot = engine.tick()
```

---

## Files worth checking

- `src/engine/rng_manager.py`
- `src/engine/models/sector.py`
- `src/engine/models/fire_propagation.py`
- `src/engine/simulation_engine.py`
