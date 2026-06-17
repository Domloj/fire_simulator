package pl.edu.agh.kis.firebackend.model.primitives;

/**
 * Compass directions discretized into 8 main sectors.
 * Provides helper to convert degrees (0-360) into a Direction.
 */
public enum Direction {
    N, NE, E, SE, S, SW, W, NW;

    public static Direction fromDegrees(double degrees) {
        // Normalize to [0,360)
        double d = ((degrees % 360.0) + 360.0) % 360.0;
        int index = (int) Math.floor((d + 22.5) / 45.0) % 8;
        return values()[index];
    }
}
