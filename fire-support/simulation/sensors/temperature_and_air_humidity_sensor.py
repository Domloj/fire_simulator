from datetime import datetime
import logging

from .sensor import Sensor
from .sensor_type import SensorType
from ..location import Location

logger = logging.getLogger(__name__)

class TemperatureAndAirHumiditySensor(Sensor):
    _sensor_type: SensorType = SensorType.TEMPERATURE_AND_AIR_HUMIDITY

    def __init__(self,
        timestamp: datetime,
        location: Location,
        sensor_id: str
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._temperature = None
        self._humidity = None
        if self._temperature is None:
            logger.debug(
                f"Sensor {self._sensor_id} of type {self._sensor_type.name} is missing temperature data!"
            )

        if self._humidity is None:
            logger.debug(
                f"Sensor {self._sensor_id} of type {self._sensor_type.name} is missing air humidity data!"
            )

    @property
    def data(self):
        result = {}
        if self._temperature is not None:
            result['temperature'] = round(self._temperature, 2)
        if self._humidity is not None:
            result['humidity'] = round(self._humidity, 2)
        return result
    
    @property
    def unit(self):
        return {"temperature" : "°C", "humidity" : "%"}


    def next(self) -> None:
        pass

    def log(self) -> None:
        if self._temperature is None and self._humidity is None:
            logger.debug(f'Sensor {self._sensor_id} of type {self._sensor_type.name} has no temperature or humidity to report.')
            return
        logger.debug(
            f"Sensor {self._sensor_id} of type {self._sensor_type.name} "
            f"reported temperature: {self._temperature if self._temperature is not None else 'N/A'} °C and air humidity: {self._humidity if self._humidity is not None else 'N/A'}%."
        )

    @property 
    def sensor_type(self):
        return self._sensor_type