package pl.edu.agh.kis.firebackend.model.events;

public record EvSectorState(
    int sectorId,
    double fireLevel,
    double burnLevel,
    double extinguishLevel,
    // Stringi mapowane na enumy FireState/ThreatLevel po stronie serwisu.
    // Trzymamy je jako String, żeby nieznana wartość z telemetrii nie wywalała
    // deserializacji całej wiadomości (i nie blokowała aktualizacji fireLevel).
    String fireState,
    String threatLevel
) { }
