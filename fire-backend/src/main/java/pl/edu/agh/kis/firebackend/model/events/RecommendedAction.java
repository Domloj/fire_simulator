package pl.edu.agh.kis.firebackend.model.events;

/**
 * Recommended action for a unit (fire brigade or forester patrol).
 * 
 * The unitType field is critical to distinguish between fire brigades and forester patrols
 * when they have overlapping IDs (e.g., both can have ID 0, 1, 2...).
 * 
 * Without unitType, there's ambiguity: unitId=0 could be fire brigade 0 or forester patrol 0.
 */
public record RecommendedAction(
    int unitId,
    int sectorId,
    String unitType  // "fireBrigade" or "foresterPatrol" - REQUIRED to avoid ID conflicts
) {
    /**
     * Create RecommendedAction with unitType for backward compatibility.
     * If unitType is null, it will be inferred from unitId (not recommended).
     */
    public RecommendedAction(int unitId, int sectorId) {
        this(unitId, sectorId, null);
    }
    
    /**
     * Check if this is a fire brigade recommendation.
     */
    public boolean isFireBrigade() {
        return "fireBrigade".equals(unitType);
    }
    
    /**
     * Check if this is a forester patrol recommendation.
     */
    public boolean isForesterPatrol() {
        return "foresterPatrol".equals(unitType);
    }
}
