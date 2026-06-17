package pl.edu.agh.kis.firebackend.model.events;

import pl.edu.agh.kis.firebackend.model.primitives.Location;

import java.util.Date;

public record EvLitterMoistureSensor(
    int sensorId,
    LitterMoistureSensorData data,
    Date timestamp,
    Location location,
    Integer sectorId
) { }
