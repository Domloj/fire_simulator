from enum import Enum

class SensorType(Enum):
    TEMPERATURE_AND_AIR_HUMIDITY = 0
    WIND_SPEED                   = 1
    WIND_DIRECTION               = 2
    LITTER_MOISTURE              = 3
    CO2                          = 4
    PM2_5                        = 5
    CAMERA                       = 6
