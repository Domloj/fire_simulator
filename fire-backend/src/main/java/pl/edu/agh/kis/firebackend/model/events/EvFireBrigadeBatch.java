package pl.edu.agh.kis.firebackend.model.events;

import java.util.List;

/**
 * Batch wrapper for Fire Brigade telemetry events.
 */
public record EvFireBrigadeBatch(List<EvFireBrigade> batch) {
}
