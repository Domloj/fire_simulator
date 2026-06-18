"""
Sensor Array for FFSim - Spec section 5.2.2.

Generates simulated sensor readings per sector configuration:
- WIND_SPEED, WIND_DIRECTION
- TEMP_HUMIDITY
- LITTER_MOISTURE
- CO2, PM2_5
- CAMERA (smoke detection)

All sensors use RngManager for determinism.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any
from src.engine.rng_manager import RngManager


class SensorType(Enum):
    """Available sensor types (spec 5.2.2)."""
    WIND_SPEED = "WIND_SPEED"
    WIND_DIRECTION = "WIND_DIRECTION"
    TEMP_HUMIDITY = "TEMP_HUMIDITY"
    LITTER_MOISTURE = "LITTER_MOISTURE"
    CO2 = "CO2"
    PM2_5 = "PM2_5"
    CAMERA = "CAMERA"


@dataclass
class SensorReading:
    """Single sensor reading (spec 5.2.2 base structure)."""

    sensor_id: int
    sensor_type: SensorType
    location: Dict[str, float]
    data: Dict[str, Any]
    timestamp: str
    sector_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "sensorId": self.sensor_id,
            "sensorType": self.sensor_type.value,
            "location": self.location,
            "data": self.data,
            "timestamp": self.timestamp,
            "sectorId": self.sector_id,
        }


@dataclass
class SensorConfig:
    """Per-sector sensor configuration."""
    
    sector_id: int
    sensor_id: int
    enabled_types: List[SensorType]
    location: Dict[str, float]
    
    baseline_temperature: float = 20.0
    baseline_humidity: float = 0.5
    baseline_moisture: float = 0.3
    baseline_co2: float = 400.0
    baseline_pm25: float = 35.0


class SensorArray:
    """
    Sensor array for entire forest map.

    Manages all sensors, generates deterministic readings per tick.
    """

    FIRE_CO2_PPM = 3000.0
    FIRE_PM25 = 450.0
    FIRE_TEMP_C = 45.0
    FIRE_HUMIDITY_DROP = 0.35
    FIRE_MOISTURE_DROP = 0.25

    def __init__(self,
                 rng: RngManager,
                 sensors_config: Optional[Dict[int, SensorConfig]] = None):
        """
        Initialize sensor array.
        
        Args:
            rng: RNG manager for deterministic readings
            sensors_config: {sector_id: SensorConfig} map
        """
        self.rng = rng
        self.sensors: Dict[int, SensorConfig] = sensors_config or {}
    
    def add_sensor(self, 
                   sector_id: int,
                   sensor_id: int,
                   sensor_types: List[SensorType],
                   location: Dict[str, float]) -> None:
        """
        Register sensor for sector.
        
        Args:
            sector_id: Sector ID
            sensor_id: Unique sensor ID
            sensor_types: List of enabled sensor types
            location: {lon, lat}
        """
        self.sensors[sensor_id] = SensorConfig(
            sector_id=sector_id,
            sensor_id=sensor_id,
            enabled_types=sensor_types,
            location=location,
        )
    
    def read_all(self,
                 timestamp: str,
                 wind_speed: float = 0.0,
                 wind_direction: float = 0.0,
                 global_temperature: float = 20.0,
                 sector_fire_levels: Optional[Dict[int, float]] = None) -> List[SensorReading]:
        """
        Read all sensors (full sensor sweep for tick).

        Args:
            timestamp: ISO timestamp
            wind_speed: Global wind speed (km/h)
            wind_direction: Global wind direction (degrees)
            global_temperature: Global temperature (°C)
            sector_fire_levels: mapa sector_id -> fire_level (0-1); odczyty na
                płonących sektorach rosną proporcjonalnie do poziomu ognia

        Returns:
            List of sensor readings
        """
        sector_fire_levels = sector_fire_levels or {}
        readings = []

        for sensor_config in self.sensors.values():
            fire_level = sector_fire_levels.get(sensor_config.sector_id, 0.0)
            for sensor_type in sensor_config.enabled_types:
                reading = self._read_sensor(
                    sensor_config=sensor_config,
                    sensor_type=sensor_type,
                    timestamp=timestamp,
                    wind_speed=wind_speed,
                    wind_direction=wind_direction,
                    global_temperature=global_temperature,
                    fire_level=fire_level,
                )
                if reading:
                    readings.append(reading)

        return readings
    
    def _read_sensor(self,
                     sensor_config: SensorConfig,
                     sensor_type: SensorType,
                     timestamp: str,
                     wind_speed: float,
                     wind_direction: float,
                     global_temperature: float,
                     fire_level: float = 0.0) -> Optional[SensorReading]:
        """
        Generate single sensor reading with realistic variation.

        Args:
            sensor_config: Sensor configuration
            sensor_type: Type of sensor to read
            timestamp: ISO timestamp
            wind_speed: Current wind speed
            wind_direction: Current wind direction
            global_temperature: Current global temperature
            fire_level: poziom ognia (0-1) na sektorze sensora; podbija odczyty
                gazów/temperatury/dymu, dzięki czemu pożar da się wykryć

        Returns:
            SensorReading or None if error
        """
        try:
            fire = max(0.0, min(1.0, fire_level))

            if sensor_type == SensorType.WIND_SPEED:
                noise = self.rng.normal(0, wind_speed * 0.05)
                speed = max(0, wind_speed + noise)
                data = {"speed": round(speed, 2)}

            elif sensor_type == SensorType.WIND_DIRECTION:
                noise = self.rng.normal(0, 10)
                angle = (wind_direction + noise) % 360
                data = {"angle": round(angle, 1)}

            elif sensor_type == SensorType.TEMP_HUMIDITY:
                temp_noise = self.rng.normal(0, 3)
                temperature = global_temperature + temp_noise + fire * self.FIRE_TEMP_C

                humidity_noise = self.rng.normal(0, 0.1)
                humidity = sensor_config.baseline_humidity + humidity_noise - fire * self.FIRE_HUMIDITY_DROP
                humidity = max(0.0, min(1.0, humidity))

                data = {
                    "temperature": round(temperature, 1),
                    "humidity": round(humidity, 3),
                }

            elif sensor_type == SensorType.LITTER_MOISTURE:
                moisture_noise = self.rng.normal(0, 0.05)
                moisture = sensor_config.baseline_moisture + moisture_noise - fire * self.FIRE_MOISTURE_DROP
                moisture = max(0.0, min(1.0, moisture))
                data = {"moisture": round(moisture, 3)}

            elif sensor_type == SensorType.CO2:
                co2_noise = self.rng.normal(0, 50)
                concentration = max(0, sensor_config.baseline_co2 + co2_noise + fire * self.FIRE_CO2_PPM)
                data = {"concentration": round(concentration, 1)}

            elif sensor_type == SensorType.PM2_5:
                pm_noise = self.rng.normal(0, sensor_config.baseline_pm25 * 0.15)
                concentration = max(0, sensor_config.baseline_pm25 + pm_noise + fire * self.FIRE_PM25)
                data = {"concentration": round(concentration, 1)}

            elif sensor_type == SensorType.CAMERA:
                smoke_prob = self.rng.random()
                detect_threshold = min(0.97, 0.05 + 0.9 * fire)
                smoke_detected = smoke_prob < detect_threshold
                smoke_level = (1 + int(fire * 4)) if smoke_detected else 0

                data = {
                    "smokeDetected": smoke_detected,
                    "smokeLevel": smoke_level,
                    "smokeLocation": sensor_config.location if smoke_detected else None,
                }

            else:
                return None

            return SensorReading(
                sensor_id=sensor_config.sensor_id,
                sensor_type=sensor_type,
                location=sensor_config.location,
                data=data,
                timestamp=timestamp,
                sector_id=sensor_config.sector_id,
            )
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Error reading sensor %d (%s): %s",
                        sensor_config.sensor_id, sensor_type.value, e)
            return None
    
    def read_by_sector(self,
                       sector_id: int,
                       timestamp: str,
                       wind_speed: float = 0.0,
                       wind_direction: float = 0.0,
                       global_temperature: float = 20.0) -> List[SensorReading]:
        """
        Read all sensors for specific sector.
        
        Args:
            sector_id: Sector to read sensors for
            timestamp: ISO timestamp
            wind_speed: Global wind speed
            wind_direction: Global wind direction
            global_temperature: Global temperature
        
        Returns:
            List of sensor readings for sector
        """
        readings = []
        
        for sensor_config in self.sensors.values():
            if sensor_config.sector_id == sector_id:
                for sensor_type in sensor_config.enabled_types:
                    reading = self._read_sensor(
                        sensor_config=sensor_config,
                        sensor_type=sensor_type,
                        timestamp=timestamp,
                        wind_speed=wind_speed,
                        wind_direction=wind_direction,
                        global_temperature=global_temperature,
                    )
                    if reading:
                        readings.append(reading)
        
        return readings
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert sensor array configuration to dict."""
        return {
            "sensor_count": len(self.sensors),
            "sensors": {
                sid: {
                    "sector_id": cfg.sector_id,
                    "enabled_types": [t.value for t in cfg.enabled_types],
                    "location": cfg.location,
                }
                for sid, cfg in self.sensors.items()
            }
        }
