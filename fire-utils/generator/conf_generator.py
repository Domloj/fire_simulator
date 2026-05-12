import json
from datetime import datetime
from enum import Enum
import random
import argparse

DEFAULT_GRID_SIZE = 6

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

def main(grid_size):
    sensors = []
    sectors = []
    fireBrigades = []

    sensor_id = 0

    lon_step = (LON_END - LON_START) / grid_size
    lat_step = (LAT_END - LAT_START) / grid_size

    for row in range(grid_size):
        for col in range(grid_size):
            sector_id = row * grid_size + col + 1
            lon_min = LON_START + col * lon_step
            lon_max = lon_min + lon_step
            lat_min = LAT_START + row * lat_step
            lat_max = lat_min + lat_step

            center_lon = (lon_min + lon_max) / 2
            center_lat = (lat_min + lat_max) / 2

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

            for sensor in SensorType:
                rand_lon = lon_min + random.uniform(0, lon_step)
                rand_lat = lat_min + random.uniform(0, lat_step)

                sensors.append({
                    "sensorId": sensor_id,
                    "sensorType": sensor.name,
                    "location": {
                        "longitude": rand_lon,
                        "latitude": rand_lat
                    },
                    "timestamp": str(int(datetime.now().timestamp() * 1000))
                })
                sensor_id += 1

            fireBrigades.append({
                "fireBrigadeId": sector_id,
                "timestamp": datetime.now().isoformat(),
                "state": "AVAILABLE",

                "baseLocation": {
                    "longitude": center_lon,
                    "latitude": center_lat
                },
                "currentLocation": {
                    "longitude": center_lon,
                    "latitude": center_lat
                }
            })

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
        "cameras": [],
        "fireBrigades": fireBrigades,
        "foresterPatrols": []
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