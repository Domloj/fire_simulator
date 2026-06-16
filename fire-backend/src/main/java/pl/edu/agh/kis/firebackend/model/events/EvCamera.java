package pl.edu.agh.kis.firebackend.model.events;

import pl.edu.agh.kis.firebackend.model.primitives.Location;

import java.util.Date;

public record EvCamera(
    int cameraId,
    String sourceUrl,
    Date timestamp,
    Location location,
    Integer sectorId
) { }
