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


@dataclass
class FirePropagationConfig:
    """Configuration for fire propagation parameters."""
    
    # Coefficients in main ignition formula
    alpha_wind: float = 0.01          # Wind influence coefficient
    beta_temperature: float = 0.02    # Temperature influence coefficient
    
    # Reference values
    reference_temperature: float = 20.0  # °C
    
    # Fire growth (section 6.2)
    spread_rate: float = 0.1          # Base spread rate per tick
    wind_multiplier_max: float = 2.0  # Max wind effect multiplier
    
    # Fuel consumption (section 6.3)
    fuel_consumption_rate: float = 0.05  # Fuel consumed per tick per fire level
    
    # Extinguishing (section 6.5)
    extinguish_threshold: float = 1.0    # When extinguish_level >= 1, sector is extinguished
    
    # Fire level (section 6.2)
    fire_growth_rate: float = 0.15       # Growth rate per tick


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
        Calculate wind direction factor using cosine of angle.
        
        Per spec 6.1: wind_component = 1 + α|w|cosθ
        - cosθ = 1 when aligned with wind (boosts ignition)
        - cosθ = -1 when against wind (reduces ignition)
        - No clamping here; clamp done in calculate_ignition_probability
        
        Returns:
            Unnormalized wind component (can be <1 or >1)
        """
        # Direction from burning sector to target
        dr = to_row - from_row
        dc = to_col - from_col
        
        # Convert to angle (0=North, 90=East, 180=South, 270=West)
        direction_angle = math.atan2(dc, -dr) * 180 / math.pi  # -dr because row increases downward
        if direction_angle < 0:
            direction_angle += 360
        
        # Angle between wind and spread direction
        wind_angle_deg = wind.direction_degrees
        angle_diff = direction_angle - wind_angle_deg
        
        # Normalize to [-180, 180]
        while angle_diff > 180:
            angle_diff -= 360
        while angle_diff < -180:
            angle_diff += 360
        
        # Convert to radians
        angle_diff_rad = math.radians(angle_diff)
        
        # cosine factor: 1.0 if aligned with wind, -1.0 if against wind, 0 perpendicular
        cos_factor = math.cos(angle_diff_rad)
        
        # spec: 1 + α|w|cosθ (unnormalized)
        wind_component = 1.0 + self.config.alpha_wind * wind.speed * cos_factor
        
        return wind_component
    
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
        Calculate probability of fire ignition (section 6.1).
        
        p_ign = clamp(0, 1, f(1-m)(1+α|w|cosθ) * ℓ_neighbor * (1+β(T-T_ref)))
        
        Args:
            target_sector: Sector that might catch fire
            neighbor_sector: Burning neighbor sector
            wind: Global wind state
            from_row, from_col: Burning sector coordinates
            to_row, to_col: Target sector coordinates
            global_temperature: Current global temperature
        
        Returns:
            Ignition probability [0, 1]
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
        Consume fuel per tick (section 6.3).
        
        f_t+1 = f_t - fireLevel * fuelConsumptionRate
        
        Args:
            sector: Sector to update
        
        Returns:
            New fuel amount [0, 1]
        """
        if not sector.is_burning():
            return sector.fuel
        
        # Fuel consumption
        fuel_consumed = sector.fire_level * self.config.fuel_consumption_rate
        new_fuel = sector.fuel - fuel_consumed
        new_fuel = max(0.0, min(1.0, new_fuel))
        
        return new_fuel
    
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
        
        If fuel <= 0, sector becomes ASH.
        
        Args:
            sector: Sector to check
        
        Returns:
            True if sector should become ASH
        """
        return sector.fuel <= 0 and sector.state == SectorState.BURNING
    
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
