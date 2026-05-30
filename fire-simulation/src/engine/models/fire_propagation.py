"""
Fire propagation model for FFSim according to spec section 6.

Core formula for ignition probability (section 6.1):
p_ign = clamp(0, 1, f(1-m)(1+α|w|cosθ) * ℓ_neighbor * (1+β(T-T_ref)))

Where:
- f: fuel amount [0,1]
- m: moisture [0,1]
- w: wind speed and direction
- θ: angle between wind direction and sector
- ℓ_neighbor: fire intensity of burning neighbor
- T: temperature
- α, β: coefficients (tunable)
- T_ref: reference temperature
"""

import math
from typing import List, Tuple, Optional
from dataclasses import dataclass
from src.engine.rng_manager import RngManager
from src.engine.models.sector import Sector, SectorState


@dataclass
class Wind:
    """Global wind state (section 7.1)."""
    
    speed: float = 0.0           # m/s or normalized [0, 1]
    direction_degrees: float = 0.0  # 0-360, where 0=North, 90=East, etc.
    
    def get_direction_radians(self) -> float:
        """Convert direction to radians."""
        return math.radians(self.direction_degrees)
    
    def clone(self) -> "Wind":
        """Create copy of wind (for snapshot semantics).
        
        Since Wind only contains floats (immutable), this is shallow copy.
        """
        return Wind(
            speed=self.speed,
            direction_degrees=self.direction_degrees
        )


@dataclass
class FirePropagationConfig:
    """Configuration for fire propagation parameters."""

    # p_ign coefficients per spec section 7 (parametry konfiguracyjne silnika)
    alpha_wind: float = 0.01          # windAlpha — wind influence coefficient (|w| in km/h)
    beta_temperature: float = 0.02    # betaTemperature — temperature coefficient

    # Reference values
    reference_temperature: float = 20.0  # °C

    # Ignition (spec section 7: ignitionBase = 0.10)
    ignition_base: float = 0.10       # Initial fireLevel of a newly ignited sector (ℓ₀)

    # Fire growth (section 2.4.2 R3)
    spread_rate: float = 0.1          # Base spread rate per tick
    wind_multiplier_max: float = 2.0  # Max wind effect multiplier

    # Fuel consumption (section 2.4.2 R3)
    # Rates per fire classification level per Klimek ISD2024:
    #   level 1 (EARLY_FIRE):   0.5 units/step  → relative multiplier 0.5
    #   level 2 (MEDIUM_FIRE):  1.0 units/step  → baseline multiplier 1.0
    #   level 3 (FULL_FIRE):    2.0 units/step  → multiplier 2.0
    #   level 4 (EXTREME_FIRE): 4.0 units/step  → multiplier 4.0
    # fuel_consumption_rate is the base (level-2 / MEDIUM_FIRE) rate [0,1]/tick.
    fuel_consumption_rate: float = 0.02
    fuel_consumption_multiplier: dict = None   # set in __post_init__

    # Extinguishing (section 2.4.2 R5)
    extinguish_threshold: float = 1.0    # When extinguish_level >= 1, sector is extinguished

    def __post_init__(self):
        if self.fuel_consumption_multiplier is None:
            # Keys are fire classification levels 1–4 per Klimek ISD2024 Table 1
            object.__setattr__(self, 'fuel_consumption_multiplier', {
                1: 0.5,   # EARLY_FIRE   — manageable by one engine
                2: 1.0,   # MEDIUM_FIRE  — baseline = fuel_consumption_rate
                3: 2.0,   # FULL_FIRE    — requires maximum crews
                4: 4.0,   # EXTREME_FIRE — exceeds local capabilities
            })


class FirePropagation:
    """Fire propagation engine."""
    
    # Cardinal directions: North, East, South, West (4-neighborhood, section 5.3)
    DIRECTIONS = [
        (-1, 0),  # North (up)
        (0, 1),   # East (right)
        (1, 0),   # South (down)
        (0, -1),  # West (left)
    ]
    
    DIRECTION_NAMES = ["North", "East", "South", "West"]
    DIRECTION_DEGREES = [0, 90, 180, 270]  # North, East, South, West
    
    # Epsilon for floating-point comparisons (prevents fuel never reaching exactly 0)
    EPSILON = 1e-6
    
    def __init__(self, rng: RngManager, config: Optional[FirePropagationConfig] = None):
        """
        Initialize fire propagation engine.
        
        Args:
            rng: Shared RNG manager for deterministic randomness
            config: Fire propagation configuration
        """
        self.rng = rng
        self.config = config or FirePropagationConfig()
    
    def calculate_wind_angle_factor(self,
                                   wind: Wind,
                                   from_row: int,
                                   from_col: int,
                                   to_row: int,
                                   to_col: int) -> float:
        """
        Wind component per spec section 2.4.1:
            wind_component = 1 + α · |w| · cosθ
        where |w| is wind speed in km/h (no normalisation per spec).
        """
        dr = to_row - from_row
        dc = to_col - from_col

        # Direction from burning sector to target (0=N, 90=E, 180=S, 270=W)
        direction_angle = math.atan2(dc, -dr) * 180 / math.pi
        if direction_angle < 0:
            direction_angle += 360

        angle_diff = direction_angle - wind.direction_degrees
        while angle_diff > 180:
            angle_diff -= 360
        while angle_diff < -180:
            angle_diff += 360

        cos_factor = math.cos(math.radians(angle_diff))
        return 1.0 + self.config.alpha_wind * wind.speed * cos_factor
    
    def calculate_ignition_probability(self,
                                      target_sector: Sector,
                                      neighbor_sector: Sector,
                                      wind: Wind,
                                      from_row: int,
                                      from_col: int,
                                      to_row: int,
                                      to_col: int,
                                      global_temperature: float) -> float:
        """
        Calculate probability of fire ignition (spec section 2.4.1, rule R1).

        Canonical formula:
            p_ign = clamp(0, 1,
                f · (1−m)
                · (1 + α · ‖w‖_norm · cosθ)
                · ℓ_neighbor
                · max(0, 1 + β·(T − T_ref))
            )

        Args:
            target_sector:    Sector that might catch fire (provides f, m, T)
            neighbor_sector:  Burning neighbour (provides ℓ_neighbor)
            wind:             Global wind state (speed in km/h, normalised internally)
            from_row/col:     Burning sector coordinates
            to_row/col:       Target sector coordinates
            global_temperature: Current global temperature (°C)

        Returns:
            Ignition probability in [0, 1]
        """
        # Pre-conditions
        if not target_sector.is_flammable():
            return 0.0
        
        if not neighbor_sector.is_burning():
            return 0.0
        
        # Component 1: Fuel and moisture
        fuel_moisture_factor = target_sector.fuel * (1.0 - target_sector.moisture)
        
        # Component 2: Wind effect (already includes 1 + α|w|cosθ)
        wind_component = self.calculate_wind_angle_factor(wind, from_row, from_col, to_row, to_col)
        
        # Component 3: Neighbor fire intensity
        neighbor_fire_factor = neighbor_sector.fire_level
        
        # Component 4: Temperature effect
        temp_diff = global_temperature - self.config.reference_temperature
        temperature_component = 1.0 + self.config.beta_temperature * temp_diff
        # IMPORTANT: Clamp to prevent negative probability at low temperatures
        temperature_component = max(0.0, temperature_component)
        
        # Combine all factors
        p_ignition = (fuel_moisture_factor * 
                     wind_component * 
                     neighbor_fire_factor * 
                     temperature_component)
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, p_ignition))
    
    def attempt_ignition(self,
                         target_sector: Sector,
                         neighbor_sector: Sector,
                         wind: Wind,
                         from_row: int,
                         from_col: int,
                         to_row: int,
                         to_col: int,
                         global_temperature: float) -> bool:
        """
        Stochastically determine if target sector catches fire.
        
        Args:
            (same as calculate_ignition_probability)
        
        Returns:
            True if fire spreads, False otherwise
        """
        p_ign = self.calculate_ignition_probability(
            target_sector, neighbor_sector, wind,
            from_row, from_col, to_row, to_col,
            global_temperature
        )
        
        # Use RNG for deterministic randomness
        return self.rng.random() < p_ign
    
    def update_fire_level(self,
                         sector: Sector,
                         sector_multiplier: float = 1.0) -> float:
        """
        Update fire level per tick (section 6.2).
        
        ℓ_t+1 = ℓ_t + spreadRate * sectorMultiplier
        (Wind effects already captured in ignition probability)
        
        Args:
            sector: Sector to update
            sector_multiplier: Sector-type effect multiplier
        
        Returns:
            New fire level [0, 1]
        """
        if not sector.is_burning():
            return sector.fire_level
        
        # Base spread rate (wind effects in ignition, not fire level growth)
        fire_add = self.config.spread_rate * sector_multiplier
        
        # Update fire level
        new_fire_level = sector.fire_level + fire_add
        new_fire_level = max(0.0, min(1.0, new_fire_level))
        
        return new_fire_level
    
    def update_fuel(self, sector: Sector) -> float:
        """
        Consume fuel per tick using level-dependent rates (article ISD2024).

        Rates per fire classification level:
            level 1 (EARLY_FIRE):   fuel_consumption_rate × 0.5
            level 2 (MEDIUM_FIRE):  fuel_consumption_rate × 1.0  (baseline)
            level 3 (FULL_FIRE):    fuel_consumption_rate × 2.0
            level 4 (EXTREME_FIRE): fuel_consumption_rate × 4.0

        f_{t+1} = f_t − fuel_consumption_rate × level_multiplier

        Args:
            sector: Sector to update

        Returns:
            New fuel amount [0, 1]
        """
        if not sector.is_burning():
            return sector.fuel

        fire_class = sector.get_fire_classification()
        multiplier = self.config.fuel_consumption_multiplier.get(fire_class, 1.0)
        fuel_consumed = self.config.fuel_consumption_rate * multiplier
        new_fuel = sector.fuel - fuel_consumed
        return max(0.0, min(1.0, new_fuel))
    
    def update_burn_level(self, sector: Sector) -> float:
        """
        Update burn level per tick (tracks cumulative burning).
        
        b_t+1 = b_t + fireLevel (clamped to [0,1])
        
        Args:
            sector: Sector to update
        
        Returns:
            New burn level [0, 1]
        """
        if not sector.is_burning():
            return sector.burn_level
        
        # Accumulate burn level
        new_burn_level = sector.burn_level + sector.fire_level * 0.1
        new_burn_level = max(0.0, min(1.0, new_burn_level))
        
        return new_burn_level
    
    def check_burnout(self, sector: Sector) -> bool:
        """
        Check if sector has burned out (section 6.4).
        
        If fuel <= EPSILON, sector becomes ASH (prevents floating-point issues).
        
        Args:
            sector: Sector to check
        
        Returns:
            True if sector should become ASH
        """
        return sector.fuel <= self.EPSILON and sector.state == SectorState.BURNING
    
    def check_extinguishment(self, sector: Sector) -> bool:
        """
        Check if fire has been extinguished (section 6.5).
        
        If extinguishLevel >= threshold, sector becomes ASH.
        
        Args:
            sector: Sector to check
        
        Returns:
            True if fire is extinguished
        """
        return (sector.extinguish_level >= self.config.extinguish_threshold and 
                sector.state == SectorState.BURNING)