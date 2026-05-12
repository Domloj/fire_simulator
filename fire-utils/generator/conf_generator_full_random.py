import json
from datetime import datetime
from enum import Enum
import random
import argparse

DEFAULT_GRID_SIZE = 10

LON_START = 20.59695852606007
LAT_START = 49.93705195152758
LON_END = 20.69067696504037
LAT_END = 49.90311928923877

class SensorType(Enum):
    TEMPERATURE_AND_AIR_HUMIDITY = 1
    WIND_SPEED = 2
    WIND_DIRECTION = 3
    LITTER_MOISTURE = 4
    PM2_5 = 5
    CO2 = 6

sensor_counts = {
    SensorType.CO2: 25,
    SensorType.LITTER_MOISTURE: 35,
    SensorType.PM2_5: 50,
    SensorType.WIND_DIRECTION: 75,
    SensorType.WIND_SPEED: 100
}

DEFAULT_FIRE_BRIGADE_COUNTS = 15
DEFAULT_FORESTER_PATROL_COUNTS = 15

def get_random_location_in_sector(sector):
    """Get a random location within a sector's bounds"""
    contours = sector["contours"]
    lon_min = min(point[0] for point in contours)
    lon_max = max(point[0] for point in contours)
    lat_min = min(point[1] for point in contours)
    lat_max = max(point[1] for point in contours)
    
    rand_lon = random.uniform(lon_min, lon_max)
    rand_lat = random.uniform(lat_min, lat_max)
    
    return rand_lon, rand_lat

def main(grid_size):
    sensors = []
    sectors = []
    fireBrigades = []
    cameras = []
    foresterPatrols = []

    sensor_id = 0
    camera_id = 0
    fire_brigade_id = 0
    forester_patrol_id = 0

    lon_step = (LON_END - LON_START) / grid_size
    lat_step = (LAT_END - LAT_START) / grid_size

    for row in range(grid_size):
        for col in range(grid_size):
            sector_id = row * grid_size + col + 1
            lon_min = LON_START + col * lon_step
            lon_max = lon_min + lon_step
            lat_min = LAT_START + row * lat_step
            lat_max = lat_min + lat_step

            contours = [
                [lon_min, lat_min],  
                [lon_min, lat_max],  
                [lon_max, lat_max],  
                [lon_max, lat_min]   
            ]

            sectors.append({
                "sectorId": sector_id,  # 1-indexed, row-major
                "row": row + 1,         # 1-indexed
                "column": col + 1,      # 1-indexed
                "sectorType": "DECIDUOUS",
                "initialState": {
                    "temperature": 20,
                    "windSpeed": 0,
                    "windDirection": "NE",
                    "airHumidity": 0,
                    "plantLitterMoisture": 0,
                    "co2Concentration": 0,
                    "pm2_5Concentration": 0, 
                    "fireLevel": 0
                }, 
                "contours": contours
            })

    
    for sensor_type, count in sensor_counts.items():
        for _ in range(count):
            sector = random.choice(sectors)
            rand_lon, rand_lat = get_random_location_in_sector(sector)
            
            sensors.append({
                "sensorId": sensor_id,
                "sensorType": sensor_type.name,
                "location": {
                    "longitude": rand_lon,
                    "latitude": rand_lat
                },
                "timestamp": str(int(datetime.now().timestamp() * 1000))
            })
            sensor_id += 1

    for _ in range(4):
        sector = random.choice(sectors)
        rand_lon, rand_lat = get_random_location_in_sector(sector)
        
        cameras.append({
            "cameraId": camera_id,
            "location": {
                "longitude": rand_lon,
                "latitude": rand_lat
            },
            "timestamp": str(int(datetime.now().timestamp() * 1000))
        })
        camera_id += 1

    for _ in range(DEFAULT_FIRE_BRIGADE_COUNTS):
        sector = random.choice(sectors)
        rand_lon, rand_lat = get_random_location_in_sector(sector)
        
        fireBrigades.append({
            "fireBrigadeId": fire_brigade_id,
            "timestamp": datetime.now().isoformat(),
            "state": "AVAILABLE",
            "baseLocation": {
                "longitude": rand_lon,
                "latitude": rand_lat
            },
            "currentLocation": {
                "longitude": rand_lon,
                "latitude": rand_lat
            }
        })
        fire_brigade_id += 1

    for _ in range(DEFAULT_FORESTER_PATROL_COUNTS):
        sector = random.choice(sectors)
        rand_lon, rand_lat = get_random_location_in_sector(sector)
        
        foresterPatrols.append({
            "foresterPatrolId": forester_patrol_id,
            "timestamp": datetime.now().isoformat(),
            "state": "AVAILABLE",
            "baseLocation": {
                "longitude": rand_lon,
                "latitude": rand_lat
            },
            "currentLocation": {
                "longitude": rand_lon,
                "latitude": rand_lat
            }
        })
        forester_patrol_id += 1

    forest_name = f"forest_{grid_size}x{grid_size}"

    configuration = {
        "forestId": -1,
        "forestName": forest_name,
        "rows": grid_size,
        "columns": grid_size,
        "location": [
            {"longitude": LON_START, "latitude": LAT_START},  
            {"longitude": LON_END, "latitude": LAT_START},    
            {"longitude": LON_END, "latitude": LAT_END},      
            {"longitude": LON_START, "latitude": LAT_END}
        ],
        "sectors": sectors,
        "sensors": sensors,
        "cameras": cameras,
        "fireBrigades": fireBrigades,
        "foresterPatrols": foresterPatrols
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{forest_name}_conf_{timestamp}.json"

    with open(filename, "w") as fp:
        json.dump(configuration, fp, indent=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate forest configuration.")
    parser.add_argument('--grid-size', type=int, default=5, help='Grid size of the forest (default: 5)')
    args = parser.parse_args()

    main(args.grid_size)