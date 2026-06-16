package pl.edu.agh.kis.firebackend.model.events;

public record EvSectorState(
    int sectorId,
    double fireLevel,
    double burnLevel,
    double extinguishLevel
) { }
