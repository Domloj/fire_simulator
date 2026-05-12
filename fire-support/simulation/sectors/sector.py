import random
from threading import Lock
import logging
from typing import List
import random
import json as jssonLib
from datetime import timedelta
import copy
import math

from simulation.sensors.sensor import Sensor
from simulation.sectors.sector_state import SectorState
from simulation.sectors.sector_type import SectorType
from simulation.sectors.fire_state import FireState
from simulation.sensors.sensor_type import SensorType
from simulation.const import const
from simulation.fire_spread import coef_generator

from simulation.sensors.temperature_and_air_humidity_sensor import TemperatureAndAirHumiditySensor
from simulation.sensors.wind_speed_sensor import WindSpeedSensor
from simulation.sensors.wind_direction_sensor import WindDirectionSensor
from simulation.sensors.co2_sensor import CO2Sensor
from simulation.sensors.litter_moisture_sensor import LitterMoistureSensor
from simulation.sensors.pm2_5_sensor import PM2_5Sensor
from simulation.cameras.camera import Camera
from simulation.location import Location

logger = logging.getLogger(__name__)

class Sector:
    __slots__ = (
        'lock', '_sector_id', '_row', '_column', '_sector_type', '_state',
        '_extinguish_level', '_fire_level', '_burn_level',
        '_number_of_fire_brigades', '_number_of_forester_patrols',
        '_fire_state', '_sensors', '_initial_temperature',
        '_adjacent_sectors',  
        '_is_modified',  
        '_coef_alpha',
        '_last_patrol_step',
    )

    def __init__(
        self,
        sector_id: int,
        row: int,
        column: int,
        sector_type: SectorType,
        initial_state: SectorState,
        fire_state=None,
        extinguish_level=0,
        fire_level=.0,
        burn_level=0,
        num_brigades=0,
        num_patrols=0,
        sensors=None,
        initial_temperature=None,
        adjacent_sectors=None,
        is_modified=False,
        coef_alpha=None,
        last_patrol_step=None
    ):
        self.lock = Lock()
        self._sector_id = sector_id
        self._row = row
        self._column = column
        self._sector_type = sector_type
        self._state = initial_state
        self._extinguish_level = extinguish_level
        self._fire_level = fire_level
        self._burn_level = burn_level
        self._number_of_fire_brigades = num_brigades
        self._number_of_forester_patrols = num_patrols
        self._sensors = sensors or []
        self._fire_state = fire_state or FireState.INACTIVE
        self._adjacent_sectors = adjacent_sectors  
        self._is_modified = is_modified  
        # Step index when this sector was last patrolled by a forester patrol.
        # None means "never patrolled" – such sectors are treated as the oldest.
        self._last_patrol_step = last_patrol_step
        
        if initial_temperature is not None:
            self._initial_temperature = initial_temperature
        elif hasattr(initial_state, 'temperature'):
            self._initial_temperature = initial_state.temperature
            
        self._coef_alpha = coef_alpha or coef_generator.calculate_alpha(self._sector_type)

    @property
    def sector_id(self) -> int:
        return self._sector_id

    @property
    def row(self) -> int:
        return self._row

    @property
    def column(self) -> int:
        return self._column
    
    @property
    def sector_type(self) -> SectorType:
        return self._sector_type

    @property
    def state(self) -> SectorState:
        return self._state
    
    @property
    def fire_level(self) -> float:
        return self._fire_level

    @property
    def extinguish_level(self) -> float:
        return self._extinguish_level

    @property
    def burn_level(self) -> float:
        return self._burn_level
    
    @fire_level.setter
    def fire_level(self, fire):
        self._fire_level = fire
        self._is_modified = True

    @burn_level.setter
    def burn_level(self, burn):
        self._burn_level = burn
        self._is_modified = True

    @extinguish_level.setter
    def extinguish_level(self, extinguish):
        self._extinguish_level = extinguish
        self._is_modified = True

    @property
    def sensors(self):
        return self._sensors
    
    @property
    def fire_state(self) -> FireState:
        return self._fire_state

    def add_sensor(self, sensor):
        self._sensors.append(sensor)
        self._is_modified = True

    def remove_sensor(self, sensor):
        self._sensors.remove(sensor)
        self._is_modified = True

    def start_fire(self):
        """Start fire with optimized random generation"""
        self._fire_level = random.randint(5, 20)
        self._fire_state = FireState.ACTIVE
        self._is_modified = True

    def update_fire_level(self):
        """Update fire level with optimized calculations (growth only)"""
        if self._fire_state != FireState.ACTIVE:
            return
            
        prev_level = self._fire_level
        fire_add = (self._fire_level/10) * self._coef_alpha * const.FIRE_LEVEL_MULTIPLIER
        new_fire_level = min(self._fire_level + fire_add, 100)

        if new_fire_level <= 0:
            self._fire_state = FireState.INACTIVE
            self._fire_level = 0
            self._is_modified = True
        elif new_fire_level != prev_level:
            self._fire_level = new_fire_level
            self._is_modified = True

    def required_fire_brigades(self):
        if self.fire_state != FireState.ACTIVE:
            return 0
        return math.ceil(self._fire_level / 3)

    def update_burn_level(self):
        """Update burn level with optimized calculations"""
        if self._fire_state != FireState.ACTIVE:
            return
            
        prev_level = self._burn_level
        
        fire_cubed = self._fire_level * self._fire_level * self._fire_level
        new_burn_level = min(self._burn_level + 0.00005 * fire_cubed, 100)
        
        if new_burn_level >= 100:
            self._fire_state = FireState.LOST
            self._fire_level = 0
            self._extinguish_level = 0
            self._is_modified = True
        elif new_burn_level != prev_level:
            self._burn_level = new_burn_level
            self._is_modified = True

    def update_sector_state(self):
        fire_influence = 0.5  # Wpływ poziomu pożaru na temperaturę
        cooling_factor = 0.02  # Naturalny spadek temperatury
        random_variation_temp = random.uniform(-0.5, 0.5)  # Zmniejszone losowe zmiany dla stabilności

        # Ograniczenie wartości fire_level do przedziału [0, 100] dla bezpieczeństwa
        self._fire_level = max(0, min(self._fire_level, 100))

        # Ustalona początkowa temperatura jako baza
        if not hasattr(self, '_initial_temperature'):
            self._initial_temperature = self._state.temperature

        # Docelowa temperatura zależna od fire_level w stosunku do początkowej wartości
        target_temperature = self._initial_temperature + (self._fire_level * 0.5)
        temperature_change = (target_temperature - self._state.temperature) * fire_influence

        # Uwzględnienie naturalnego chłodzenia i losowych fluktuacji
        self._state.temperature += temperature_change - (self._state.temperature * cooling_factor) + random_variation_temp
        self._state.temperature = max(10, min(self._state.temperature, self._initial_temperature + 80))  # Ograniczenie zakresu
        # logger.info(f"Sector {self.sector_id} - Temperature: {self._state.temperature}")

        # Wilgotność powietrza – maleje wraz z pożarem, ale nie spada poniżej 5%
        humidity_change = self._fire_level * 0.4 + random.uniform(-2, 2)
        self._state.air_humidity -= humidity_change
        self._state.air_humidity = max(5, min(self._state.air_humidity, 100))
        # logger.info(f"Sector {self.sector_id} - Air Humidity: {self._state.air_humidity}")

        # Stężenie CO2 – wzrost z ograniczonym wpływem losowości, kontrola wzrostu
        co2_change = (self._fire_level ** 1.1) - (self._state.co2_concentration * 0.01) + random.uniform(-5, 5)
        self._state.co2_concentration += co2_change
        self._state.co2_concentration = max(300, self._state.co2_concentration)  # Naturalny poziom CO2 minimum
        # logger.info(f"Sector {self.sector_id} - CO2 Concentration: {self._state.co2_concentration}")

        # Wilgotność ściółki – gwałtowny spadek, ograniczenie przed całkowitym wysuszeniem
        litter_moisture_change = self._fire_level * 0.5 + random.uniform(-1, 1)
        self._state.plant_litter_moisture -= litter_moisture_change
        self._state.plant_litter_moisture = max(2, min(self._state.plant_litter_moisture, 100))
        # logger.info(f"Sector {self.sector_id} - Plant Litter Moisture: {self._state.plant_litter_moisture}")

        # Stężenie PM2.5 – eksponencjalny wzrost ograniczony kontrolą
        pm_increase = (self._fire_level ** 1.3 / 25) - (self._state.pm2_5_concentration * 0.02) + random.uniform(-0.3, 0.3)
        self._state.pm2_5_concentration += pm_increase
        self._state.pm2_5_concentration = max(5, self._state.pm2_5_concentration)  # Minimalny poziom PM2.5
        # logger.info(f"Sector {self.sector_id} - PM2.5 Concentration: {self._state.pm2_5_concentration}")

        # Prędkość wiatru – kontrolowany wzrost i fluktuacja dla realizmu
        wind_increase = (self._fire_level * 0.025) - (self._state.wind_speed * 0.01) + random.uniform(-0.2, 0.2)
        self._state.wind_speed += wind_increase
        self._state.wind_speed = max(0, min(self._state.wind_speed, 50))  # Ograniczenie prędkości wiatru
        # logger.info(f"Sector {self.sector_id} - Wind Speed: {self._state.wind_speed}")


    def update_sector(self):
        self.update_fire_level()
        self.update_burn_level()
        self.update_sector_state()

    def update_sensors(self):
        for sensor in self.sensors:
            sensor._timestamp += timedelta(seconds=1)
            if isinstance(sensor, PM2_5Sensor):
                sensor._pm2_5 = self._state.pm2_5_concentration + random.uniform(-0.1, 0.1)
            elif isinstance(sensor, TemperatureAndAirHumiditySensor):                
                sensor._temperature = self._state.temperature + random.uniform(-0.5, 0.5)
                sensor._humidity = self._state.air_humidity + random.uniform(-0.5, 0.5)
            elif isinstance(sensor, LitterMoistureSensor):
                sensor._litter_moisture = self._state.plant_litter_moisture + random.uniform(-0.5, 0.5)
            elif isinstance(sensor, CO2Sensor):
                sensor._co2 = self._state.co2_concentration + random.uniform(-0.5, 0.5)
            elif isinstance(sensor, WindSpeedSensor) :              
                sensor._wind_speed = self._state.wind_speed + random.uniform(-0.5, 0.5)
            elif isinstance(sensor, WindDirectionSensor):
                sensor._wind_direction = self._state.wind_direction
            elif isinstance(sensor, Camera):
                sensor._camera_data.smoke_detected = 1 if self.fire_level > 0 else 0
                sensor._camera_data.smoke_level = self.fire_level
                
    def make_jsons(self):
        jsons_by_type = {}

        for sensor in self.sensors:
            json = {
                "sensorId": sensor.sensor_id,
                "timestamp": sensor._timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                "sensorType": sensor.sensor_type.name,
                "location": {
                    "longitude": sensor._location.longitude,
                    "latitude": sensor._location.latitude,
                },
                "data": sensor.data
            }
            
            if sensor.sensor_type.name not in jsons_by_type:
                jsons_by_type[sensor.sensor_type.name] = []
            
            jsons_by_type[sensor.sensor_type.name].append(json)
        
        return jsons_by_type

    def make_sector_json(self):
        return {
            "sectorId":         int(self.sector_id), 
            # "fireState":      0,
            "fireLevel":        float(self.fire_level),
            "burnLevel":        float(self.burn_level), 
            "extinguishLevel":  float(self.extinguish_level)
        }

    def clone(self):
        # Create a new instance with the same core attributes
        cloned = Sector(
            sector_id=self._sector_id,
            row=self._row,
            column=self._column,
            sector_type=self._sector_type,
            initial_state=copy.deepcopy(self._state),
            fire_state=self._fire_state,
            extinguish_level=self._extinguish_level,
            fire_level=self._fire_level,
            burn_level=self._burn_level,
            num_brigades=self._number_of_fire_brigades,
            num_patrols=self._number_of_forester_patrols,
            sensors=copy.deepcopy(self._sensors),
            initial_temperature=self._initial_temperature,
            is_modified=self._is_modified,
            coef_alpha=self._coef_alpha,
            last_patrol_step=self._last_patrol_step
        )
        
        # The new instance will create its own lock
        
        # Copy cached adjacent sectors if they exist
        # if hasattr(self, '_adjacent_sectors') and self._adjacent_sectors is not None:
        #     cloned._adjacent_sectors = copy.copy(self._adjacent_sectors)
            
        return cloned