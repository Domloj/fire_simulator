package pl.edu.agh.kis.firebackend.model.events;

import pl.edu.agh.kis.firebackend.model.primitives.Location;

import java.util.Date;

public record EvCO2Sensor(
    int sensorId,
    CO2SensorData data,
    Date timestamp,
    Location location,
    Integer sectorId
) { }
