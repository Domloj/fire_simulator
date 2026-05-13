import logging
from datetime import datetime

from src.engine.models.sensors.sensor_type import SensorType
from src.engine.models.core.location import Location
from src.engine.models.sensors.camera_data import CameraData
from src.engine.models.sensors.sensor import Sensor

class WindSpeedSensor(Sensor):
    _sensor_type: SensorType = SensorType.WIND_SPEED

    def __init__(
        self,        
        timestamp: datetime,
        location: Location,
        sensor_id: str,        
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._wind_speed = 5.0  # Default wind speed in m/s
    
    @property
    def data(self) -> float:
        speed_val = round(self._wind_speed, 2) if self._wind_speed is not None else 5.0
        return {
            "windSpeed": speed_val
        }
    
    @property
    def unit(self) -> str:
        return {
            "windSpeed":"m/s"
        }

    def next(self) -> None:
        pass

    def log(self) -> None:
        logging.debug(
            f'Sensor {self._sensor_id} of type {WindSpeedSensor.sensor_type} '
            f'reported wind speed: {self._wind_speed:.2f} m/s.'
        )

    @property 
    def sensor_type(self):
        return self._sensor_type