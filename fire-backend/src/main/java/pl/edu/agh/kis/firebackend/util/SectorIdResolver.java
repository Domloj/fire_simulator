package pl.edu.agh.kis.firebackend.util;

import lombok.AllArgsConstructor;
import pl.edu.agh.kis.firebackend.model.primitives.Location;
import pl.edu.agh.kis.firebackend.service.model.simulation.Sector;

import java.util.List;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SectorIdResolver 
{
    private static final Logger log = LoggerFactory.getLogger(SectorIdResolver.class);

    public static Optional<Integer> resolveSectorId(List<Sector> sectors, Location location)
    {
        Optional<Sector> direct = sectors
            .stream()
            .filter(sector -> locationInBounds(calculateBounds(sector), location))
            .findFirst();

        if (direct.isPresent()) {
            return Optional.of(direct.get().sectorId);
        }

        double minDist = Double.POSITIVE_INFINITY;
        Sector nearest = null;
        for (Sector sector : sectors) {
            Bounds b = calculateBounds(sector);
            double centerLon = (b.east + b.west) / 2.0;
            double centerLat = (b.south + b.north) / 2.0;
            double dLon = centerLon - location.longitude();
            double dLat = centerLat - location.latitude();
            double dist = Math.sqrt(dLon * dLon + dLat * dLat);
            if (dist < minDist) {
                minDist = dist;
                nearest = sector;
            }
        }

        if (nearest != null) {
            log.debug("Location {} not within any sector bounds; falling back to nearest sector {} (dist={})", location, nearest.sectorId, minDist);
            return Optional.of(nearest.sectorId);
        }

        log.debug("Location {} not found in any sector and no sectors available", location);
        return Optional.empty();
    }

    private static class Bounds 
    {
        public double east;
        public double north;
        public double south;
        public double west;

        public Bounds(double east, double north, double south, double west) {
            this.east = east;
            this.north = north;
            this.south = south;
            this.west = west;
        }
    }

    private static Bounds calculateBounds(Sector sector) 
    {
        Bounds acc = new Bounds
        (
            Double.POSITIVE_INFINITY, 
            Double.NEGATIVE_INFINITY, 
            Double.POSITIVE_INFINITY, 
            Double.NEGATIVE_INFINITY
        );

        for (List<Double> contour : sector.contours) 
        {
            Double longitude = contour.get(0);
            Double latitude = contour.get(1);

            if (longitude < acc.east) 
            {
                acc.east = longitude;
            }

            if (latitude > acc.north) 
            {
                acc.north = latitude;
            }

            if (latitude < acc.south) 
            {
                acc.south = latitude;
            }

            if (longitude > acc.west) 
            {
                acc.west = longitude;
            }
        }
        return acc;
    }

    private static boolean locationInBounds(Bounds bounds, Location location) 
    {
        double lon = location.longitude();
        double lat = location.latitude();
        final double EPS = 1e-7; // tolerate tiny precision errors

        return 
            (bounds.east - EPS <= lon && lon <= bounds.west + EPS) &&
            (bounds.south - EPS <= lat && lat <= bounds.north + EPS);
    }

}
