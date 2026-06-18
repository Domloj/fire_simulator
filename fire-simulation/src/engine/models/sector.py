"""
Sector model for FFSim according to spec section 5.2.

Each sector has:
- moisture: [0, 1] - wilgotność
- fuel: [0, 1] - paliwo
- fireLevel: [0, 1] - intensywność ognia
- burnLevel: [0, 1] - spalanie (nieodwracalne)
- extinguishLevel: [0, 1] - gaszenie
- temperature: R - temperatura
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
    
    DECIDUOUS = "DECIDUOUS"        # alpha 0.8
    CONIFEROUS = "CONIFEROUS"      # 1.2
    MIXED = "MIXED"                # 1.0
    FIELD = "FIELD"                # 1.5
    FALLOW = "FALLOW"              # 1.2
    WATER = "WATER"                # 0.5
    UNTRACKED = "UNTRACKED"        # 1.0


@dataclass
class Sector:
    """
    Sector domain entity per FFSim spec section 5.2.
    
    Main simulation domain object representing a forest sector.
    """
    
    sector_id: int
    row: int
    column: int
    sector_type: SectorType
    
    state: SectorState = SectorState.DORMANT
    
    moisture: float = 0.0           # [0, 1] - wilgotność
    fuel: float = 1.0               # [0, 1] - paliwo
    fire_level: float = 0.0         # [0, 1] - intensywność ognia
    burn_level: float = 0.0         # [0, 1] - spalanie
    extinguish_level: float = 0.0   # [0, 1] - gaszenie
    temperature: float = 20.0       # R - temperatura
    
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


    def get_fire_classification(self) -> int:
        """
        Return fire classification level 0-5 per fire classification table (ISD2024).

        Used by telemetry and the support system to determine required
        firefighting resources.
        """
        if self.state in (SectorState.ASH, SectorState.EXTINGUISHED):
            return 5
        if self.state != SectorState.BURNING:
            return 0
        if self.fire_level <= 0.0:
            return 0
        if self.fire_level <= 0.25:
            return 1
        if self.fire_level <= 0.50:
            return 2
        if self.fire_level <= 0.75:
            return 3
        return 4

    def get_fire_state_name(self) -> str:
        """
        Zwraca string FireState zgodny z enumem backendu (FFSup):
        NON_COMBUSTED / MILD / MODERATE / FULL / SEVERE / COMBUSTED / EXTINGUISHED.

        Klasyfikacja liczbowa (Tabela 1 z artykułu) zostaje bez zmian, mapujemy
        tylko nazwy na te, które backend potrafi sparsować. COMBUSTED i
        EXTINGUISHED rozróżniamy na poziomie 5, żeby backend znał przyczynę
        (wypalony vs ugaszony).
        """
        _names = {
            0: "NON_COMBUSTED",
            1: "MILD",
            2: "MODERATE",
            3: "FULL",
            4: "SEVERE",
        }
        level = self.get_fire_classification()
        if level == 5:
            return "EXTINGUISHED" if self.state == SectorState.EXTINGUISHED else "COMBUSTED"
        return _names[level]

    def get_threat_level(self, dist_to_fire: Optional[int] = None) -> str:
        """
        Zwraca poziom zagrożenia pożarowego sektora zgodny z enumem backendu:
        LOW / MEDIUM / HIGH / VERY_HIGH / CRITICAL.

        To metryka monitoringu: zagrożenie wynika głównie z odległości od
        czynnego pożaru (sektory przy froncie są najbardziej zagrożone), a
        modyfikuje je suchość sektora. Daleko od ognia poziom spada do LOW, więc
        zagrożenie tworzy czytelny gradient promieniujący wokół pożaru zamiast
        zalewać całą mapę jednym kolorem.

        Args:
            dist_to_fire: odległość (w sektorach) do najbliższego płonącego
                sektora; None gdy poza zasięgiem albo brak pożaru
        """
        if self.state in (SectorState.ASH, SectorState.EXTINGUISHED):
            return "LOW"
        if self.state == SectorState.BURNING and self.fire_level > 0.0:
            return {1: "HIGH", 2: "VERY_HIGH", 3: "VERY_HIGH", 4: "CRITICAL"}[
                self.get_fire_classification()
            ]

        if dist_to_fire is None or dist_to_fire >= 4:
            base = 0
        elif dist_to_fire == 1:
            base = 3
        elif dist_to_fire == 2:
            base = 2
        else:                 
            base = 1

        dryness = 1.0 - self.moisture
        if dryness > 0.7:
            base += 1
        elif dryness < 0.3:
            base -= 1

        levels = ["LOW", "MEDIUM", "HIGH", "VERY_HIGH", "CRITICAL"]
        idx = max(0, min(base, 4))
        return levels[idx]

    def get_flammability_coefficient(self) -> float:
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