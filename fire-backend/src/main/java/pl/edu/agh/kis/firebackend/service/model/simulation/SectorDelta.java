package pl.edu.agh.kis.firebackend.service.model.simulation;

import pl.edu.agh.kis.firebackend.model.primitives.Direction;

import java.util.List;

/**
 * Partial sector update containing only changed fields.
 * This allows sending only what changed instead of the entire sector.
 */
public record SectorDelta(
    int sectorId,
    // Only include fields that changed (null means unchanged)
    Double fireLevel,
    Double burnLevel,
    Double extinguishLevel,
    Double temperature,
    Double windSpeed,
    Direction windDirection,
    Double airHumidity,
    Double plantLitterMoisture,
    Double co2Concentration,
    Double pm2_5Concentration,
    // Contours only sent if changed
    List<List<Double>> contours,
    // Assigned brigades only sent if changed
    List<Integer> assignedBrigades
) {
    public boolean hasChanges() {
        return fireLevel != null || burnLevel != null || extinguishLevel != null ||
               temperature != null || windSpeed != null || windDirection != null ||
               airHumidity != null || plantLitterMoisture != null ||
               co2Concentration != null || pm2_5Concentration != null ||
               contours != null || assignedBrigades != null;
    }
}
