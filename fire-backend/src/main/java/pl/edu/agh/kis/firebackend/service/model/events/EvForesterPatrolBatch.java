package pl.edu.agh.kis.firebackend.service.model.events;

import java.util.List;

public record EvForesterPatrolBatch(
        List<EvForestPatrol> batch) {
}
