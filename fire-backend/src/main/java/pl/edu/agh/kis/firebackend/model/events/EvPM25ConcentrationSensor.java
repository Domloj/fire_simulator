package pl.edu.agh.kis.firebackend.model.events;

import pl.edu.agh.kis.firebackend.model.primitives.Location;

import java.util.Date;

public record EvPM25ConcentrationSensor(
    int sensorId,
    PM25ConcentrationSensorData data,
    Date timestamp,
    Location location,
    Integer sectorId
) { }
