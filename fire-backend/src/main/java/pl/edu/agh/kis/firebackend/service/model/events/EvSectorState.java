package pl.edu.agh.kis.firebackend.service.model.events;

public record EvSectorState(
    int sectorId,
    // int fireState, 
    double fireLevel,
    double burnLevel, 
    double extinguishLevel
) { }