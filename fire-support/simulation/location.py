from dataclasses import dataclass


@dataclass
class Location:
    latitude: float
    longitude: float

    def clone(self):
        return Location(latitude=self.latitude, longitude=self.longitude)
