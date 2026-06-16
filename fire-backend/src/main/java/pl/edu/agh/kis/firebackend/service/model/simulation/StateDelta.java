package pl.edu.agh.kis.firebackend.service.model.simulation;

import pl.edu.agh.kis.firebackend.model.events.RecommendedAction;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * Delta update containing only changed data since last update.
 * This reduces network traffic and improves performance.
 */
public record StateDelta(
    String forestName,
    Date timestamp,
    long tick,
    // Only changed sectors (partial updates - only changed fields)
    List<SectorDelta> changedSectors,
    // Only changed/added fire brigades
    List<FireBrigade> changedFireBrigades,
    // Only changed/added forester patrols
    List<ForesterPatrol> changedForesterPatrols,
    // Only new recommendations
    List<RecommendedAction> newRecommendations,
    // Removed entities (IDs only)
    List<Integer> removedSectors,
    List<Integer> removedFireBrigades,
    List<Integer> removedForesterPatrols
) {
    public static StateDelta empty(String forestName, Date timestamp, long tick) {
        return new StateDelta(
            forestName,
            timestamp,
            tick,
            new ArrayList<>(),
            new ArrayList<>(),
            new ArrayList<>(),
            new ArrayList<>(),
            new ArrayList<>(),
            new ArrayList<>(),
            new ArrayList<>()
        );
    }
}
