from datetime import datetime
import logging

from src.engine.models.sensors.sensor_type import SensorType
from src.engine.models.core.location import Location
from src.engine.models.sensors.camera_data import CameraData
from src.engine.models.sensors.sensor import Sensor

class TemperatureAndAirHumiditySensor(Sensor):
    _sensor_type: SensorType = SensorType.TEMPERATURE_AND_AIR_HUMIDITY

    def __init__(
        self,
        timestamp: datetime,
        location: Location,
        sensor_id: str
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._temperature = 20.0  # Default temperature in °C
        self._humidity = 50.0  # Default humidity in %

    @property
    def data(self):
        temp = round(self._temperature, 2) if self._temperature is not None else 20.0
        hum = round(self._humidity, 2) if self._humidity is not None else 50.0
        return {"temperature" : temp, "humidity" : hum}
    
    @property
    def unit(self):
        return {"temperature" : "°C", "humidity" : "%"}


    def next(self) -> None:
        pass

    def log(self) -> None:
        logging.debug(
            f"Sensor {self._sensor_id} of type {TemperatureAndAirHumiditySensor.sensor_type} "
            f"reported temperature: {self._temperature:.2f} °C and air humidity: {self._temperature:.2f}%."
        )

    @property 
    def sensor_type(self):
        return self._sensor_type