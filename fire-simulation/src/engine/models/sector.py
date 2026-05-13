"""
Sector model for FFSim according to spec section 5.2.

Each sector has:
- moisture: [0, 1] - wilgotność
- fuel: [0, 1] - paliwo
- fireLevel: [0, 1] - intensywność ognia
- burnLevel: [0, 1] - spalanie (nieodwracalne)
- extinguishLevel: [0, 1] - gaszenie
- temperature: ℝ - temperatura
- sectorType: enum - typ sektora
"""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict
import copy


class SectorState(Enum):
    """State machine for sector (section 5.1 L-system)."""
    
    DORMANT = "DORMANT"      # F - sektor niepalący się
    BURNING = "BURNING"      # B - sektor płonący
    EXTINGUISHED = "EXTINGUISHED" # ugaszony
    ASH = "ASH"              # A - sektor wypalony/ugaszony (nieodwracalny)


class SectorType(Enum):
    """Vegetation types with flammability characteristics."""
    
    DECIDUOUS = "DECIDUOUS"        # α ~ 0.8
    CONIFEROUS = "CONIFEROUS"      # α ~ 1.2
    MIXED = "MIXED"                # α ~ 1.0
    FIELD = "FIELD"                # α ~ 1.5
    FALLOW = "FALLOW"              # α ~ 1.2
    WATER = "WATER"                # α ~ 0.5
    UNTRACKED = "UNTRACKED"        # α ~ 1.0


@dataclass
class Sector:
    """
    Sector domain entity per FFSim spec section 5.2.
    
    Main simulation domain object representing a forest sector.
    """
    
    # Identifiers
    sector_id: int
    row: int
    column: int
    sector_type: SectorType
    
    # State machine (section 5.1)
    state: SectorState = SectorState.DORMANT
    
    # Parameters (section 5.2)
    moisture: float = 0.0           # [0, 1] - wilgotność
    fuel: float = 1.0               # [0, 1] - paliwo
    fire_level: float = 0.0         # [0, 1] - intensywność ognia
    burn_level: float = 0.0         # [0, 1] - spalanie
    extinguish_level: float = 0.0   # [0, 1] - gaszenie
    temperature: float = 20.0       # R - temperatura
    
    # Optional location data
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    
    def __post_init__(self):
        """Validate sector parameters."""
        assert 0 <= self.moisture <= 1, f"Moisture must be [0,1], got {self.moisture}"
        assert 0 <= self.fuel <= 1, f"Fuel must be [0,1], got {self.fuel}"
        assert 0 <= self.fire_level <= 1, f"Fire level must be [0,1], got {self.fire_level}"
        assert 0 <= self.burn_level <= 1, f"Burn level must be [0,1], got {self.burn_level}"
        assert 0 <= self.extinguish_level <= 1, f"Extinguish level must be [0,1], got {self.extinguish_level}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert sector to dictionary for JSON serialization."""
        data = asdict(self)
        data["sector_type"] = self.sector_type.value
        data["state"] = self.state.value
        return data
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Sector":
        """Create sector from dictionary."""
        data_copy = copy.deepcopy(data)
        data_copy["sector_type"] = SectorType(data_copy["sector_type"])
        data_copy["state"] = SectorState(data_copy["state"])
        return Sector(**data_copy)
    
    def clone(self) -> "Sector":
        """Create immutable copy of sector."""
        return copy.deepcopy(self)
    
    def is_flammable(self) -> bool:
        """Check if sector can catch fire."""
        return (
            self.state == SectorState.DORMANT and
            self.fuel > 0 and
            self.sector_type != SectorType.WATER
        )
    
    def is_burning(self) -> bool:
        """Check if sector is currently burning."""
        return self.state == SectorState.BURNING
    
    def get_flammability_coefficient(self) -> float:
        """
        Get α coefficient based on vegetation type (section 6.1).
        
        Returns:
            Flammability coefficient for fire spread calculation
        """
        coefficients = {
            SectorType.FIELD: 1.5,
            SectorType.FALLOW: 1.2,
            SectorType.CONIFEROUS: 1.2,
            SectorType.MIXED: 1.0,
            SectorType.DECIDUOUS: 0.8,
            SectorType.WATER: 0.0,
            SectorType.UNTRACKED: 1.0,
        }
        return coefficients.get(self.sector_type, 1.0)
    
    def __repr__(self) -> str:
        return (
            f"Sector(id={self.sector_id}, type={self.sector_type.value}, "
            f"state={self.state.value}, fire={self.fire_level:.2f}, fuel={self.fuel:.2f})"
        )
