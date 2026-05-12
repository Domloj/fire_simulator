from dataclasses import dataclass

from simulation.sectors.geographic_direction import GeographicDirection


@dataclass(frozen=False)
class SectorState:
    temperature: float | None
    wind_speed: float | None
    wind_direction: GeographicDirection | None
    air_humidity: float | None 
    plant_litter_moisture: float | None  
    co2_concentration: float | None  
    pm2_5_concentration: float | None 
