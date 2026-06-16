package pl.edu.agh.kis.firebackend.service.model.configuration;

import java.util.Date;

import pl.edu.agh.kis.firebackend.service.model.ForesterPatrolState;
import pl.edu.agh.kis.firebackend.model.primitives.Location;

public record ConfForesterPatrol(
    int foresterPatrolId,
    Date timestamp,
    ForesterPatrolState state,
    Location baseLocation,
    Location currentLocation
) { }
