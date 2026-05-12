import json
import random

from datetime import datetime
from typing import TypeAlias
from typing import Tuple
from typing import List, Tuple, Optional
import logging

from simulation.sectors.sector import Sector
from simulation.location import Location
from simulation.sectors.sector_state import SectorState
from simulation.sectors.sector_type import SectorType
from simulation.sectors.geographic_direction import GeographicDirection
from simulation.sensors.temperature_and_air_humidity_sensor import TemperatureAndAirHumiditySensor
from simulation.sensors.wind_speed_sensor import WindSpeedSensor
from simulation.sensors.wind_direction_sensor import WindDirectionSensor
from simulation.sensors.co2_sensor import CO2Sensor
from simulation.sensors.litter_moisture_sensor import LitterMoistureSensor
from simulation.sensors.pm2_5_sensor import PM2_5Sensor
from simulation.cameras.camera import Camera
from simulation.forester_patrols.forester_patrol import ForesterPatrol
from simulation.fire_brigades.fire_brigade import FireBrigade
from simulation.fire_brigades.fire_brigade_state import FIREBRIGADE_STATE
from simulation.forester_patrols.forest_patrols_state import FORESTERPATROL_STATE
from simulation.sectors.fire_state import FireState

logger = logging.getLogger(__name__)

ForestMapCornerLocations: TypeAlias = tuple[Location, Location, Location, Location] 

class ForestMap:
    def __init__(
        self,
        forest_id: str,
        forest_name: str,
        rows: int,
        columns: int,
        location: ForestMapCornerLocations,
        sectors: list[list[Sector]],
        foresterPatrols: list[ForesterPatrol],
        fireBrigades: list[FireBrigade]
    ):
        self._forest_id = forest_id
        self._forest_name = forest_name
        self._rows = rows
        self._columns = columns
        self._location = location
        self._sectors = sectors
        self._forester_patrols = foresterPatrols
        self._fire_brigades = fireBrigades

    def update_extinguish_levels(self):
        """Centrally recalculate extinguish levels based on current agent positions and states."""
        # Reset all sectors
        for row in self._sectors:
            for sector in row:
                if sector.extinguish_level > 0:
                    sector.extinguish_level = 0.0
                    sector._is_modified = True
                sector._number_of_fire_brigades = 0
        
        # Count current fire brigades in EXECUTING state
        for brigade in self._fire_brigades:
            if brigade.state.value == "executing":
                sector = self.find_sector(brigade.location)
                if sector:
                    sector._number_of_fire_brigades += 1
                    sector.extinguish_level = sector._number_of_fire_brigades * 5.0
                    sector._is_modified = True

    @classmethod
    def from_conf(cls, conf):
        location = cls._parse_locations(conf["location"])
        sectors = cls._parse_sectors(conf)
        bounds = cls._calculate_bounds(location, conf["rows"], conf["columns"])

        cls._assign_sensors_to_sectors(conf["sensors"], sectors, bounds)
        cls._assign_cameras_to_sectors(conf["cameras"], sectors, bounds)

        brigades = cls._parse_fire_brigades(conf)
        patrols = cls._parse_forester_patrols(conf)
        
        return cls(
            forest_id=conf["forestId"],
            forest_name=conf["forestName"],
            rows=conf["rows"],
            columns=conf["columns"],
            location=location,
            sectors=sectors,
            foresterPatrols=patrols,
            fireBrigades=brigades
        )

    @staticmethod
    def _parse_locations(locations_conf):
        return tuple(Location(**location) for location in locations_conf)

    @staticmethod
    def _parse_sectors(conf):
        rows = conf["rows"]
        columns = conf["columns"]
        sectors = [[None for _ in range(columns)] for _ in range(rows)]
        
        # Simple heuristic from fire-simulation: if max value matches total, it's likely 1-indexed
        is_one_indexed = any(s.get("row") == rows or s.get("column") == columns for s in conf["sectors"])

        for val in conf["sectors"]:
            initial_state = SectorState(
                temperature            = val["initialState"]["temperature"],
                wind_speed             = val["initialState"]["windSpeed"],
                wind_direction         = GeographicDirection[val["initialState"]["windDirection"]],
                air_humidity           = val["initialState"]["airHumidity"],
                plant_litter_moisture  = val["initialState"]["plantLitterMoisture"],
                co2_concentration      = val["initialState"]["co2Concentration"],
                pm2_5_concentration    = val["initialState"]["pm2_5Concentration"],
            )
            
            raw_row = val["row"]
            raw_col = val["column"]

            if is_one_indexed:
                row = raw_row - 1
                col = raw_col - 1
            else:
                row = raw_row
                col = raw_col
            
            # Ensure indices are within bounds
            row = max(0, min(rows - 1, row))
            col = max(0, min(columns - 1, col))

            # Match fire-simulation ID logic: row * columns + col + 1
            calculated_sector_id = row * columns + col + 1
            config_sector_id = val.get("sectorId")
            sector_id = config_sector_id if config_sector_id is not None else calculated_sector_id
            
            sectors[row][col] = Sector(
                sector_id=sector_id,
                row=row,
                column=col,
                sector_type=SectorType[val["sectorType"]],
                initial_state=initial_state,
                fire_level=float(val["initialState"].get("fireLevel", 0.0)),
                fire_state=FireState.ACTIVE if (val["initialState"].get("fireLevel", 0.0) > 0) else FireState.INACTIVE
            )
        return sectors
    
    def _parse_fire_brigades(conf):
        fire_brigades = []
        for idx, fb_data in enumerate(conf["fireBrigades"]):
            fire_brigade_id = str(fb_data.get("fireBrigadeId", idx))
            timestamp = datetime.fromisoformat(fb_data["timestamp"]) 
            state = FIREBRIGADE_STATE[fb_data["state"]]

            base_location = Location(
                longitude=float(fb_data["baseLocation"]["longitude"]),
                latitude=float(fb_data["baseLocation"]["latitude"])
            )

            current_location = None

            if fb_data.get("currentLocation") is None:
                logger.warning(f"[MAP] FireBrigade {fire_brigade_id}: missing currentLocation, defaulting to baseLocation")
                current_location = Location(
                    longitude=base_location.longitude,
                    latitude=base_location.latitude
                )
            else:
                current_location = Location(
                    longitude=float(fb_data["currentLocation"]["longitude"]),
                    latitude=float(fb_data["currentLocation"]["latitude"])
                )

            fire_brigades.append(FireBrigade(
                fire_brigade_id=fire_brigade_id,
                timestamp=timestamp,
                initial_state=state,
                base_location=base_location,
                initial_location=current_location
            ))

        return fire_brigades
    
    def _parse_forester_patrols(conf):
        foresterPatrols = []
        for idx, fb_data in enumerate(conf["foresterPatrols"]):
            forester_patrol_id = str(fb_data.get("foresterPatrolId", idx))
            timestamp = datetime.fromisoformat(fb_data["timestamp"]) 
            state = FORESTERPATROL_STATE[fb_data["state"]]

            base_location = Location(
                longitude=float(fb_data["baseLocation"]["longitude"]),
                latitude=float(fb_data["baseLocation"]["latitude"])
            )

            current_location = None

            if fb_data.get("currentLocation") is None:
                logger.warning(f"[MAP] ForesterPatrol {forester_patrol_id}: missing currentLocation, defaulting to baseLocation")
                current_location = Location(
                    longitude=base_location.longitude,
                    latitude=base_location.latitude
                )
            else:
                current_location = Location(
                    longitude=float(fb_data["currentLocation"]["longitude"]),
                    latitude=float(fb_data["currentLocation"]["latitude"])
                )

            foresterPatrols.append(ForesterPatrol(
                forester_patrol_id=forester_patrol_id,
                timestamp=timestamp,
                initial_state=state,
                base_location=base_location,
                initial_location=current_location
            ))

        return foresterPatrols

    @staticmethod
    def _calculate_bounds(locations, rows, columns):
        min_lat = min(location.latitude for location in locations)
        min_lon = min(location.longitude for location in locations)
        diff_lat = max(location.latitude for location in locations) - min_lat
        diff_lon = max(location.longitude for location in locations) - min_lon
        return {
            "min_lat": min_lat,
            "min_lon": min_lon,
            "width_sectors": diff_lon / columns,
            "height_sectors": diff_lat / rows
        }
    
    @staticmethod
    def _assign_sensors_to_sectors(sensors, sectors, bounds):
        for sensor in sensors:
            sensor_obj = ForestMap._create_sensor(sensor)
            if not sensor_obj:
                continue

            sensor_location = Location(**sensor["location"])
            
            # Map latitude to row: min_lat (South) -> row = rows-1, max_lat (North) -> row = 0
            lat_span = bounds["height_sectors"] * len(sectors)
            if lat_span > 0:
                lat_interpolation = (sensor_location.latitude - bounds["min_lat"]) / lat_span
                row = int((1 - lat_interpolation) * len(sectors))
            else:
                row = 0
                
            if bounds["width_sectors"] > 0:
                column = int((sensor_location.longitude - bounds["min_lon"]) / bounds["width_sectors"])
            else:
                column = 0
                
            row = max(0, min(len(sectors) - 1, row))
            column = max(0, min(len(sectors[0]) - 1, column))

            if sectors[row][column]:
                sectors[row][column].add_sensor(sensor_obj)

    @staticmethod
    def _assign_cameras_to_sectors(cameras, sectors, bounds):
        for camera in cameras:
            camera_obj = ForestMap._create_camera(camera)

            if not camera_obj:
                continue

            camera_location = Location(**camera["location"])
            
            # Map latitude to row: min_lat (South) -> row = rows-1, max_lat (North) -> row = 0
            lat_span = bounds["height_sectors"] * len(sectors)
            lon_span = bounds["width_sectors"] * len(sectors[0])
            
            if lat_span > 0:
                lat_interpolation = (camera_location.latitude - bounds["min_lat"]) / lat_span
                row = int((1 - lat_interpolation) * len(sectors))
            else:
                row = 0
                
            if lon_span > 0:
                column = int((camera_location.longitude - bounds["min_lon"]) / bounds["width_sectors"])
            else:
                column = 0
            
            row = max(0, min(len(sectors) - 1, row))
            column = max(0, min(len(sectors[0]) - 1, column))

            if sectors[row][column]:
                sectors[row][column].add_sensor(camera_obj)

    @staticmethod
    def _create_sensor(sensor_conf):
        sensor_arguments = {
            "timestamp": datetime.now(),
            "location": Location(sensor_conf["location"]["latitude"], sensor_conf["location"]["longitude"]),
            "sensor_id": sensor_conf["sensorId"],
        }
        match sensor_conf["sensorType"]:
            case "TEMPERATURE_AND_AIR_HUMIDITY":
                return TemperatureAndAirHumiditySensor(**sensor_arguments)
            case "WIND_SPEED":
                return WindSpeedSensor(**sensor_arguments)
            case "WIND_DIRECTION":
                return WindDirectionSensor(**sensor_arguments)
            case "LITTER_MOISTURE":
                return LitterMoistureSensor(**sensor_arguments)
            case "PM2_5":
                return PM2_5Sensor(**sensor_arguments)
            case "CO2":
                return CO2Sensor(**sensor_arguments)
            case _:
                return None

    @staticmethod
    def _create_camera(camera_conf):
        return Camera(datetime.now(), Location(camera_conf["location"]["latitude"], camera_conf["location"]["longitude"]), camera_conf["cameraId"])

    @property
    def foresterPatrols(self):
        return self._forester_patrols
    
    @property
    def fireBrigades(self):
        return self._fire_brigades

    @property
    def forest_id(self) -> str:
        return self._forest_id

    @property
    def forest_name(self) -> str:
        return self._forest_name

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def location(self) -> ForestMapCornerLocations:
        return self._location

    @property
    def sectors(self) -> list[list[Sector]]:
        return self._sectors
    
    def start_new_fire(self) -> Sector:
        row = random.choice(self.sectors)
        sector = random.choice(row)
        sector.start_fire()

        return sector        
    
    def get_sector_with_max_burn_level(self) -> Sector:
        max_burn_level = 0
        max_burn_sector = None
        for row in self._sectors:
            for sector in row:
                if sector.burn_level > max_burn_level:
                    max_burn_level = sector.burn_level
                    max_burn_sector = sector
        return max_burn_sector
    
    def get_sector_location(self, sector: Sector) -> Location:
        """
        Compute the geographic center of a given sector based on the four map corners.
        Assumes row 0 is the southernmost row (bottom).
        """
        lats = [loc.latitude for loc in self._location]
        lons = [loc.longitude for loc in self._location]
        
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        total_lon_span = max_lon - min_lon
        total_lat_span = max_lat - min_lat

        sector_width = total_lon_span / self._columns
        sector_height = total_lat_span / self._rows

        center_lon = min_lon + (sector.column + 0.5) * sector_width
        # Row 0 is at min_lat, Row rows-1 is at max_lat
        center_lat = min_lat + (sector.row + 0.5) * sector_height

        return Location(longitude=center_lon, latitude=center_lat)

    def get_sector(self, sector_id: int) -> Sector:
        for row in self._sectors:
            for sector in row:
                if sector.sector_id == sector_id:
                    return sector
        return None

    def find_sector(self, location: Location):
        """Find sector based on location. Row 0 is South."""
        lats = [loc.latitude for loc in self._location]
        lons = [loc.longitude for loc in self._location]
        
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        lat_span = max_lat - min_lat
        lon_span = max_lon - min_lon

        if lat_span == 0 or lon_span == 0:
            return None  

        lat_interpolation = (location.latitude - min_lat) / lat_span
        lon_interpolation = (location.longitude - min_lon) / lon_span

        # height_index 0 is South (min_lat), so interpolation 0.0 -> index 0
        height_index = int(lat_interpolation * self.rows)
        width_index = int(lon_interpolation * self.columns)

        height_index = max(0, min(self.rows - 1, height_index))
        width_index = max(0, min(self.columns - 1, width_index))

        return self._sectors[height_index][width_index]


    def get_adjacent_sectors(self, sector: Sector) -> list[Tuple[Sector, GeographicDirection]]:
        row = sector.row
        column = sector.column
        adjacent_sectors = []

        directions = [
            (-1, 0, GeographicDirection.N),
            (-1, 1, GeographicDirection.NE),
            (0, 1, GeographicDirection.E),
            (1, 1, GeographicDirection.SE),
            (1, 0, GeographicDirection.S),
            (1, -1, GeographicDirection.SW),
            (0, -1, GeographicDirection.W),
            (-1, -1, GeographicDirection.NW)
        ]

        for delta_row, delta_column, direction in directions:
            new_row = row + delta_row
            new_column = column + delta_column

            if 0 <= new_row < len(self.sectors) and 0 <= new_column < len(self.sectors[new_row]):
                adjacent_sectors.append((self.sectors[new_row][new_column], direction))

        return adjacent_sectors

    def update_sectors(self, new_sectors: List[Sector]):
        id_map = {s.sector_id: s for s in new_sectors}
        for row in self.sectors:
            for i, s in enumerate(row):
                row[i] = id_map[s.sector_id]

    def clone(self) -> 'ForestMap':
        cloned_sectors = [
            [sector.clone() for sector in row]
            for row in self._sectors
        ]

        cloned_brigades = [brigade.clone() for brigade in self._fire_brigades]
        cloned_patrols = [patrol.clone() for patrol in self._forester_patrols]

        return ForestMap(
            forest_id=self._forest_id,
            forest_name=self._forest_name,
            rows=self._rows,
            columns=self._columns,
            location=tuple(Location(loc.latitude, loc.longitude) for loc in self._location),
            sectors=cloned_sectors,
            foresterPatrols=cloned_patrols,
            fireBrigades=cloned_brigades
        )