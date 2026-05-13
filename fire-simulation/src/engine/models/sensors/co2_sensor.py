import logging
from datetime import datetime

from src.engine.models.sensors.sensor_type import SensorType
from src.engine.models.core.location import Location
from src.engine.models.sensors.camera_data import CameraData
from src.engine.models.sensors.sensor import Sensor

class CO2Sensor(Sensor):
    _sensor_type: SensorType = SensorType.CO2

    def __init__(
        self,
        timestamp: datetime,
        location: Location,
        sensor_id: str,
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._co2 = 400.0  # Default CO2 concentration in μg/m³

    @property
    def unit(self):
        return {"co2" : "μg/m³"}
    
    @property
    def data(self):
        co2_val = round(self._co2, 2) if self._co2 is not None else 400.0
        return {"co2" : co2_val}

    def next(self) -> None:
        pass

    def log(self) -> None:
        logging.debug(
            f'Sensor {self._sensor_id} of type {CO2Sensor.sensor_type} '
            f'reported CO₂ concentration: {self._co2:.2f} μg/m³.'
        )

    @property 
    def sensor_type(self):
        return self._sensor_type