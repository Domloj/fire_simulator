import logging
from datetime import datetime

from simulation.sensors.sensor import Sensor
from simulation.sensors.sensor_type import SensorType
from simulation.location import Location

logger = logging.getLogger(__name__)


class CO2Sensor(Sensor):
    _sensor_type: SensorType = SensorType.CO2

    def __init__(
        self,
        timestamp: datetime,
        location: Location,
        sensor_id: str,
    ):
        Sensor.__init__(self, timestamp, location, sensor_id)
        self._co2 = None
        if self._co2 is None:
            # Missing CO2 is expected in some setups; keep it quiet unless debugging
            logger.debug(
                f"Sensor {self._sensor_id} of type {self._sensor_type.name} is missing CO₂ concentration data!"
            )

    @property
    def unit(self):
        return {"co2" : "μg/m³"}
    
    @property
    def data(self):
        if self._co2 is None:
            return {}
        return {"co2" : round(self._co2, 2)}

    def next(self) -> None:
        pass

    def log(self) -> None:
        if self._co2 is None:
            logger.debug(
                f'Sensor {self._sensor_id} of type {self._sensor_type.name} has no CO₂ value to report.'
            )
        else:
            logger.debug(
                f'Sensor {self._sensor_id} of type {self._sensor_type.name} '
                f'reported CO₂ concentration: {self._co2:.2f} μg/m³.'
            )

    @property 
    def sensor_type(self):
        return self._sensor_type