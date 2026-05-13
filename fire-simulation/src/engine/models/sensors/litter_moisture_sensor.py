import logging
from datetime import datetime

from src.engine.models.sensors.sensor_type import SensorType
from src.engine.models.core.location import Location
from src.engine.models.sensors.camera_data import CameraData
from src.engine.models.sensors.sensor import Sensor

class LitterMoistureSensor(Sensor):
    _sensor_type: SensorType = SensorType.LITTER_MOISTURE

    def __init__(
        self,
        timestamp: datetime,
        location: Location,
        sensor_id: str,
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._litter_moisture = 30.0  # Default litter moisture in %
    
    @property
    def unit(self):
        return {"litter_moisture" : "%"}
    
    @property
    def data(self):
        litter_val = round(self._litter_moisture, 2) if self._litter_moisture is not None else 30.0
        return {"litter_moisture" : litter_val}

    def next(self) -> None:
        pass

    def log(self) -> None:
        logging.debug(
            f'Sensor {self._sensor_id} of type {LitterMoistureSensor.sensor_type} '
            f'reported litter moisture: {self._litter_moisture:.2f}%.'
        )

    @property 
    def sensor_type(self):
        return self._sensor_type