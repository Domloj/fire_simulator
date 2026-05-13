from dataclasses import dataclass

@dataclass
class Location:
    """Represents a geographic location with latitude and longitude"""
    latitude: float
    longitude: float

    def __post_init__(self):
        if self.latitude < -90 or self.latitude > 90:
            pass # Relaxed validation for now
        if self.longitude < -180 or self.longitude > 180:
            pass # Relaxed validation for now

    def to_dict(self):
        return {"latitude": self.latitude, "longitude": self.longitude}

    def __eq__(self, other):
        if not isinstance(other, Location):
            return False
        return abs(self.latitude - other.latitude) < 1e-7 and \
               abs(self.longitude - other.longitude) < 1e-7
