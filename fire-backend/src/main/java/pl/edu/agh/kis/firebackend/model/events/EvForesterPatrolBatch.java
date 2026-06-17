package pl.edu.agh.kis.firebackend.model.events;

import java.util.List;

/**
 * Batch wrapper for Forester Patrol telemetry events.
 */
public record EvForesterPatrolBatch(List<EvForestPatrol> batch) {
}
