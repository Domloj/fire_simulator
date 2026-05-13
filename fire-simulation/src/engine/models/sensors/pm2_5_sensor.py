import logging
from datetime import datetime

from src.engine.models.sensors.sensor_type import SensorType
from src.engine.models.core.location import Location
from src.engine.models.sensors.camera_data import CameraData
from src.engine.models.sensors.sensor import Sensor

class PM2_5Sensor(Sensor):
    _sensor_type: SensorType = SensorType.PM2_5

    def __init__(
        self,
        timestamp: datetime,
        location: Location,
        sensor_id: str,
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._pm2_5 = 10.0  # Default PM2.5 concentration in ppm

    @property
    def data(self):
        pm_val = round(self._pm2_5, 2) if self._pm2_5 is not None else 10.0
        return {"pm2_5" : pm_val}

    @property
    def unit(self) -> str:
        return {"pm2_5" : "ppm"}

    def next(self) -> None:
        pass

    def log(self) -> None:
        logging.debug(
            f'Sensor {self._sensor_id} of type {PM2_5Sensor.sensor_type} '
            f'reported PM2.5 concentration: {self._pm2_5:.2f} ppm.'
        )

    @property 
    def sensor_type(self):
        return self._sensor_type