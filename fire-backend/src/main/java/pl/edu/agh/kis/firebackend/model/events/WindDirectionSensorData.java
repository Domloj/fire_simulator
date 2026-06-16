package pl.edu.agh.kis.firebackend.model.events;

import pl.edu.agh.kis.firebackend.model.primitives.Direction;

/**
 * Wind direction as reported by sensor. The raw value may be either a numeric
 * degrees value (e.g., 270.0) or a cardinal abbreviation (e.g., "NE").
 */
public record WindDirectionSensorData(
    String windDirection
) {
    /**
     * Convert the reported value to degrees (0-360).
     * Accepts numeric strings or common compass abbreviations (N, NE, E, ...).
     */
    public double toDegrees() {
        if (windDirection == null) {
            throw new IllegalArgumentException("windDirection is null");
        }
        String s = windDirection.trim();
        try {
            return Double.parseDouble(s);
        } catch (NumberFormatException e) {
            switch (s.toUpperCase()) {
                case "N": return 0.0;
                case "NE": return 45.0;
                case "E": return 90.0;
                case "SE": return 135.0;
                case "S": return 180.0;
                case "SW": return 225.0;
                case "W": return 270.0;
                case "NW": return 315.0;
                default:
                    throw new IllegalArgumentException("Unrecognized windDirection: " + s);
            }
        }
    }

    /**
     * Convert to discrete Direction enum.
     */
    public Direction toDirection() {
        return Direction.fromDegrees(toDegrees());
    }
}
