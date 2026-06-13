"""
Sensor Array for FFSim — Spec section 5.2.2.

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
    location: Dict[str, float]  # {lon, lat}
    data: Dict[str, Any]       # Type-specific
    timestamp: str             # ISO format
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "sensorId": self.sensor_id,
            "sensorType": self.sensor_type.value,
            "location": self.location,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class SensorConfig:
    """Per-sector sensor configuration."""
    
    sector_id: int
    sensor_id: int                      # Base ID (can have multiple sensors per sector)
    enabled_types: List[SensorType]     # Which sensors are active
    location: Dict[str, float]          # {lon, lat}
    
    # Baseline values (for realistic variation)
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
                 global_temperature: float = 20.0) -> List[SensorReading]:
        """
        Read all sensors (full sensor sweep for tick).
        
        Args:
            timestamp: ISO timestamp
            wind_speed: Global wind speed (km/h)
            wind_direction: Global wind direction (degrees)
            global_temperature: Global temperature (°C)
        
        Returns:
            List of sensor readings
        """
        readings = []
        
        for sensor_config in self.sensors.values():
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
    
    def _read_sensor(self,
                     sensor_config: SensorConfig,
                     sensor_type: SensorType,
                     timestamp: str,
                     wind_speed: float,
                     wind_direction: float,
                     global_temperature: float) -> Optional[SensorReading]:
        """
        Generate single sensor reading with realistic variation.
        
        Args:
            sensor_config: Sensor configuration
            sensor_type: Type of sensor to read
            timestamp: ISO timestamp
            wind_speed: Current wind speed
            wind_direction: Current wind direction
            global_temperature: Current global temperature
        
        Returns:
            SensorReading or None if error
        """
        try:
            if sensor_type == SensorType.WIND_SPEED:
                # Add local variation (±5%)
                noise = self.rng.normal(0, wind_speed * 0.05)
                speed = max(0, wind_speed + noise)
                data = {"speed": round(speed, 2)}
            
            elif sensor_type == SensorType.WIND_DIRECTION:
                # Add local variation (±10 degrees)
                noise = self.rng.normal(0, 10)
                angle = (wind_direction + noise) % 360
                data = {"angle": round(angle, 1)}
            
            elif sensor_type == SensorType.TEMP_HUMIDITY:
                # Temperature: ±3°C variation
                temp_noise = self.rng.normal(0, 3)
                temperature = global_temperature + temp_noise
                
                # Humidity: ±10% variation
                humidity_noise = self.rng.normal(0, 0.1)
                humidity = max(0, min(1.0, sensor_config.baseline_humidity + humidity_noise))
                
                data = {
                    "temperature": round(temperature, 1),
                    "humidity": round(humidity, 3),
                }
            
            elif sensor_type == SensorType.LITTER_MOISTURE:
                # Moisture: ±0.05 variation
                moisture_noise = self.rng.normal(0, 0.05)
                moisture = max(0, min(1.0, sensor_config.baseline_moisture + moisture_noise))
                data = {"moisture": round(moisture, 3)}
            
            elif sensor_type == SensorType.CO2:
                # CO2: ±50 ppm variation
                co2_noise = self.rng.normal(0, 50)
                concentration = max(0, sensor_config.baseline_co2 + co2_noise)
                data = {"concentration": round(concentration, 1)}
            
            elif sensor_type == SensorType.PM2_5:
                # PM2.5: ±15% variation
                pm_noise = self.rng.normal(0, sensor_config.baseline_pm25 * 0.15)
                concentration = max(0, sensor_config.baseline_pm25 + pm_noise)
                data = {"concentration": round(concentration, 1)}
            
            elif sensor_type == SensorType.CAMERA:
                # Camera: smoke detection (probabilistic)
                # Smoke likelihood increases with fire activity
                smoke_prob = self.rng.random()  # [0, 1)
                smoke_detected = smoke_prob < 0.1  # 10% baseline detection
                smoke_level = int(self.rng.uniform(0, 5)) if smoke_detected else 0
                
                data = {
                    "smokeDetected": smoke_detected,
                    "smokeLevel": smoke_level,
                    "smokeLocation": None,  # TODO: integrate with sector fire state
                }
            
            else:
                return None
            
            return SensorReading(
                sensor_id=sensor_config.sensor_id,
                sensor_type=sensor_type,
                location=sensor_config.location,
                data=data,
                timestamp=timestamp,
            )
        
        except Exception as e:
            # Log and skip this sensor reading
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
