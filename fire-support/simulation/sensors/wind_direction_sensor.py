import logging
from datetime import datetime

from simulation.sectors.geographic_direction import GeographicDirection
from simulation.sensors.sensor import Sensor
from simulation.sensors.sensor_type import SensorType
from simulation.location import Location

logger = logging.getLogger(__name__)

class WindDirectionSensor(Sensor):
    _sensor_type: SensorType = SensorType.WIND_DIRECTION

    def __init__(self,        
        timestamp: datetime,
        location: Location,
        sensor_id: str,       
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._wind_direction:GeographicDirection | None = None
        if self._wind_direction is None:
            logger.debug(
                f"Sensor {self._sensor_id} of type {self._sensor_type.name} is missing wind direction data!"
            )

    

    @property
    def wind_direction(self) -> GeographicDirection | None:
        return self._wind_direction

    
    @property
    def data(self):
        if self._wind_direction is None:
            return {}
        return {"windDirection": self._wind_direction.name}

    @property
    def unit(self):
        return {"windDirection": None}

    def next(self) -> None:
        pass

    def log(self) -> None:
        if self._wind_direction is None:
            logger.debug(f"Sensor {self._sensor_id} of type {self._sensor_type.name} has no wind direction to report.")
        else:
            logger.debug(
                f"Sensor {self._sensor_id} of type {self._sensor_type.name} "
                f"reported wind direction: {self._wind_direction.name}."
            )

    @property 
    def sensor_type(self):
        return self._sensor_type