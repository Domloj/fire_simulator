import logging
from datetime import datetime

from src.engine.models.sensors.sensor_type import SensorType
from src.engine.models.core.location import Location
from src.engine.models.map.geographic_direction import GeographicDirection
from src.engine.models.sensors.camera_data import CameraData
from src.engine.models.sensors.sensor import Sensor

class WindDirectionSensor(Sensor):
    _sensor_type: SensorType = SensorType.WIND_DIRECTION

    def __init__(
        self,        
        timestamp: datetime,
        location: Location,
        sensor_id: str,       
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._wind_direction: GeographicDirection | None = GeographicDirection.N  # Default to North

    @property
    def wind_direction(self) -> GeographicDirection | None:
        return self._wind_direction

    @property
    def data(self):
        direction_name = self.wind_direction.name if self.wind_direction is not None else "N"
        return {"windDirection": direction_name}

    @property
    def unit(self):
        return {"windDirection": None}

    def next(self) -> None:
        pass

    def log(self) -> None:
        logging.debug(
            f"Sensor {self._sensor_id} of type {WindDirectionSensor.sensor_type} "
            f"reported wind direction: {self._wind_direction.name}."
        )

    @property 
    def sensor_type(self):
        return self._sensor_type