import logging
from datetime import datetime

from simulation.sensors.sensor import Sensor
from simulation.sensors.sensor_type import SensorType
from simulation.location import Location

logger = logging.getLogger(__name__)

class PM2_5Sensor(Sensor):
    _sensor_type: SensorType = SensorType.PM2_5

    def __init__(self,
        timestamp: datetime,
        location: Location,
        sensor_id: str,
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._pm2_5 = None
        if self._pm2_5 is None:
            logger.debug(
                f"Sensor {self._sensor_id} of type {self._sensor_type.name} is missing PM2.5 concentration data!"
            )

    @property
    def data(self):
        if self._pm2_5 is None:
            return {}
        return {"pm2_5" : round(self._pm2_5, 2)}

    @property
    def unit(self) -> str:
        return {"pm2_5" : "ppm"}

    def next(self) -> None:
        pass

    def log(self) -> None:
        if self._pm2_5 is None:
            logger.debug(f'Sensor {self._sensor_id} of type {self._sensor_type.name} has no PM2.5 value to report.')
        else:
            logger.debug(
                f'Sensor {self._sensor_id} of type {self._sensor_type.name} '
                f'reported PM2.5 concentration: {self._pm2_5:.2f} ppm.'
            )

    @property 
    def sensor_type(self):
        return self._sensor_type