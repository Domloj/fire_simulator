package pl.edu.agh.kis.firebackend.service.model.events;

import pl.edu.agh.kis.firebackend.service.model.ForesterPatrolState;
import pl.edu.agh.kis.firebackend.model.primitives.Location;

import java.util.Date;

public record EvForestPatrol(
    int foresterPatrolId,
    ForesterPatrolState state,
    Date timestamp,
    Location location,
    Integer sectorId
) { }

