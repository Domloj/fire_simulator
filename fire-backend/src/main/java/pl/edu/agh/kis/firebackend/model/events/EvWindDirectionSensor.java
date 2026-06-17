package pl.edu.agh.kis.firebackend.model.events;

import pl.edu.agh.kis.firebackend.model.primitives.Location;

import java.util.Date;

public record EvWindDirectionSensor(
    int sensorId,
    WindDirectionSensorData data,
    Date timestamp,
    Location location,
    Integer sectorId
) { }
