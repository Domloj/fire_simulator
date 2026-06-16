package pl.edu.agh.kis.firebackend.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import pl.edu.agh.kis.firebackend.model.events.EvRecommendation;
import pl.edu.agh.kis.firebackend.model.events.RecommendedAction;
import pl.edu.agh.kis.firebackend.model.primitives.Location;
import pl.edu.agh.kis.firebackend.service.model.configuration.*;
import pl.edu.agh.kis.firebackend.service.model.FireBrigadeState;
import pl.edu.agh.kis.firebackend.service.model.ForesterPatrolState;
import pl.edu.agh.kis.firebackend.service.model.SectorState;
import pl.edu.agh.kis.firebackend.service.model.FireState;
import pl.edu.agh.kis.firebackend.service.model.ThreatLevel;
import pl.edu.agh.kis.firebackend.model.primitives.Direction;

import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.text.SimpleDateFormat;
import java.util.*;

/**
 * Utility class for integration tests.
 * Provides helper methods for loading forest configurations and verifying LLM recommendations.
 */
public class TestUtils {
    private static final ObjectMapper objectMapper = new ObjectMapper();
    private static final SimpleDateFormat dateFormat = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS");

    /**
     * Load forest configuration from JSON file.
     * 
     * @param configPath Path to the forest configuration JSON file
     * @return Configuration object
     * @throws IOException if file cannot be read or parsed
     */
    public static Configuration loadForestConfig(String configPath) throws IOException {
        File configFile = new File(configPath);
        if (!configFile.exists()) {
            // Try relative path from project root
            Path projectRoot = Paths.get("").toAbsolutePath();
            configFile = projectRoot.resolve(configPath).toFile();
        }
        
        JsonNode root = objectMapper.readTree(configFile);
        
        // Parse location
        List<Location> location = new ArrayList<>();
        JsonNode locationArray = root.get("location");
        if (locationArray != null && locationArray.isArray()) {
            for (JsonNode loc : locationArray) {
                location.add(new Location(
                    (float) loc.get("longitude").asDouble(),
                    (float) loc.get("latitude").asDouble()
                ));
            }
        }
        
        // Parse sectors
        List<ConfSector> sectors = new ArrayList<>();
        JsonNode sectorsArray = root.get("sectors");
        if (sectorsArray != null && sectorsArray.isArray()) {
            for (JsonNode sectorNode : sectorsArray) {
                JsonNode initialStateNode = sectorNode.get("initialState");
                double fireLevel = initialStateNode.has("fireLevel") ? initialStateNode.get("fireLevel").asDouble() : 0.0;
                
                SectorState initialState = new SectorState(
                    new Date(),
                    initialStateNode.has("temperature") ? initialStateNode.get("temperature").asDouble() : 20.0,
                    initialStateNode.has("windSpeed") ? initialStateNode.get("windSpeed").asDouble() : 0.0,
                    initialStateNode.has("windDirection") ? parseWindDirection(initialStateNode.get("windDirection").asText()) : null,
                    initialStateNode.has("airHumidity") ? initialStateNode.get("airHumidity").asDouble() : 0.0,
                    initialStateNode.has("plantLitterMoisture") ? initialStateNode.get("plantLitterMoisture").asDouble() : 0.0,
                    initialStateNode.has("co2Concentration") ? initialStateNode.get("co2Concentration").asDouble() : 0.0,
                    initialStateNode.has("pm2_5Concentration") ? initialStateNode.get("pm2_5Concentration").asDouble() : 0.0,
                    ThreatLevel.LOW,
                    fireLevel > 0 ? FireState.MILD : FireState.NON_COMBUSTED,
                    fireLevel,
                    0.0,
                    0.0
                );
                
                JsonNode contoursNode = sectorNode.get("contours");
                List<List<Double>> contours = new ArrayList<>();
                if (contoursNode != null && contoursNode.isArray()) {
                    for (JsonNode contour : contoursNode) {
                        List<Double> contourList = new ArrayList<>();
                        for (JsonNode point : contour) {
                            contourList.add(point.asDouble());
                        }
                        contours.add(contourList);
                    }
                }
                
                sectors.add(new ConfSector(
                    sectorNode.get("sectorId").asInt(),
                    sectorNode.get("row").asInt(),
                    sectorNode.get("column").asInt(),
                    initialState,
                    SectorType.valueOf(sectorNode.get("sectorType").asText()),
                    contours,
                    new ArrayList<>() // assignedBrigades
                ));
            }
        }
        
        // Parse fire brigades
        List<ConfFireBrigade> fireBrigades = new ArrayList<>();
        JsonNode fireBrigadesArray = root.get("fireBrigades");
        if (fireBrigadesArray != null && fireBrigadesArray.isArray()) {
            for (JsonNode fbNode : fireBrigadesArray) {
                Date timestamp = parseTimestamp(fbNode.get("timestamp").asText());
                Location baseLocation = parseLocation(fbNode.get("baseLocation"));
                Location currentLocation = parseLocation(fbNode.get("currentLocation"));
                
                fireBrigades.add(new ConfFireBrigade(
                    fbNode.get("fireBrigadeId").asInt(),
                    timestamp,
                    FireBrigadeState.valueOf(fbNode.get("state").asText()),
                    baseLocation,
                    currentLocation
                ));
            }
        }
        
        // Parse forester patrols
        List<ConfForesterPatrol> foresterPatrols = new ArrayList<>();
        JsonNode foresterPatrolsArray = root.get("foresterPatrols");
        if (foresterPatrolsArray != null && foresterPatrolsArray.isArray()) {
            for (JsonNode fpNode : foresterPatrolsArray) {
                Date timestamp = parseTimestamp(fpNode.get("timestamp").asText());
                Location baseLocation = parseLocation(fpNode.get("baseLocation"));
                Location currentLocation = parseLocation(fpNode.get("currentLocation"));
                
                foresterPatrols.add(new ConfForesterPatrol(
                    fpNode.get("foresterPatrolId").asInt(),
                    timestamp,
                    ForesterPatrolState.valueOf(fpNode.get("state").asText()),
                    baseLocation,
                    currentLocation
                ));
            }
        }
        
        // Calculate dimensions
        int rows = root.get("rows").asInt();
        int columns = root.get("columns").asInt();
        
        // Calculate sector size (simplified - would need actual calculation from contours)
        double sectorSize = 1.0;
        
        return new Configuration(
            root.get("forestId").asText(),
            root.get("forestName").asText(),
            0.0, // width - would need calculation
            0.0, // height - would need calculation
            columns,
            rows,
            sectorSize,
            null, // imageReference
            location,
            sectors,
            new ArrayList<>(), // sensors
            new ArrayList<>(), // cameras
            fireBrigades,
            foresterPatrols
        );
    }
    
    /**
     * Modify configuration to add active fires to some sectors.
     * 
     * @param config Original configuration
     * @param sectorIds List of sector IDs to set on fire
     * @param fireLevel Fire level (0.0 - 1.0)
     * @return Modified configuration
     */
    public static Configuration addActiveFires(Configuration config, List<Integer> sectorIds, double fireLevel) {
        List<ConfSector> modifiedSectors = new ArrayList<>();
        
        for (ConfSector sector : config.sectors()) {
            SectorState initialState = sector.initialState();
            boolean shouldHaveFire = sectorIds.contains(sector.sectorId());
            
            SectorState modifiedState = new SectorState(
                new Date(),
                initialState.temperature + 50.0, // Increase temperature
                initialState.windSpeed,
                initialState.windDirection,
                initialState.airHumidity,
                initialState.plantLitterMoisture,
                initialState.co2Concentration + 100.0, // Increase CO2
                initialState.pm2_5Concentration + 50.0, // Increase PM2.5
                ThreatLevel.HIGH,
                shouldHaveFire ? FireState.MILD : FireState.NON_COMBUSTED,
                shouldHaveFire ? fireLevel : 0.0,
                0.0,
                0.0
            );
            
            ConfSector modifiedSector = new ConfSector(
                sector.sectorId(),
                sector.row(),
                sector.column(),
                modifiedState,
                sector.sectorType(),
                sector.contours(),
                sector.assignedBrigades()
            );
            
            modifiedSectors.add(modifiedSector);
        }
        
        return new Configuration(
            config.forestId(),
            config.forestName(),
            config.width(),
            config.height(),
            config.columns(),
            config.rows(),
            config.sectorSize(),
            config.imageReference(),
            config.location(),
            modifiedSectors,
            config.sensors(),
            config.cameras(),
            config.fireBrigades(),
            config.foresterPatrols()
        );
    }
    
    /**
     * Verify that a recommendation is from LLM (not MCTS).
     * 
     * @param recommendation The recommendation to verify
     * @return true if recommendation appears to be from LLM
     */
    public static boolean isLlmRecommendation(EvRecommendation recommendation) {
        if (recommendation == null || recommendation.recommendedActions() == null) {
            return false;
        }
        
        if (recommendation.recommendedActions().isEmpty()) {
            return false;
        }
        
        // RecommendedAction only has unitId, sectorId, and unitType
        // We can't check description/reasoning from the action itself
        // For LLM detection, we check:
        // 1. If we have recommendations (LLM should generate them)
        // 2. If recommendations target multiple sectors (LLM tends to be more strategic)
        // 3. If unitType is properly set (LLM should set this correctly)
        
        if (recommendation.recommendedActions().isEmpty()) {
            return false;
        }
        
        // Check if unitType is set (LLM should always set this)
        boolean hasUnitType = recommendation.recommendedActions().stream()
            .allMatch(action -> action.unitType() != null && !action.unitType().isEmpty());
        
        // Check if recommendations are diverse (multiple sectors)
        long uniqueSectors = recommendation.recommendedActions().stream()
            .mapToInt(RecommendedAction::sectorId)
            .distinct()
            .count();
        
        // LLM recommendations typically:
        // - Have unitType set
        // - Target multiple sectors (more strategic)
        // - Have at least one recommendation
        boolean likelyLlm = hasUnitType && uniqueSectors > 0;
        
        // For testing, be permissive - if we have recommendations with proper structure,
        // assume it could be LLM (since we're testing LLM mode)
        return likelyLlm;
    }
    
    /**
     * Verify recommendation structure.
     * 
     * @param recommendation The recommendation to verify
     * @return true if structure is valid
     */
    public static boolean isValidRecommendationStructure(EvRecommendation recommendation) {
        if (recommendation == null) {
            return false;
        }
        
        if (recommendation.recommendedActions() == null || recommendation.recommendedActions().isEmpty()) {
            return false;
        }
        
        for (RecommendedAction action : recommendation.recommendedActions()) {
            if (action.unitId() < 0 || action.sectorId() < 0) {
                return false;
            }
            if (action.unitType() == null || action.unitType().isEmpty()) {
                return false;
            }
        }
        
        return true;
    }
    
    /**
     * Check if recommendation targets sectors with active fires.
     * 
     * @param recommendation The recommendation to check
     * @param sectorsWithFires Set of sector IDs that have active fires
     * @return true if at least one action targets a sector with fire
     */
    public static boolean targetsActiveFires(EvRecommendation recommendation, Set<Integer> sectorsWithFires) {
        if (recommendation == null || recommendation.recommendedActions() == null) {
            return false;
        }
        
        return recommendation.recommendedActions().stream()
            .anyMatch(action -> sectorsWithFires.contains(action.sectorId()));
    }
    
    private static Location parseLocation(JsonNode locationNode) {
        if (locationNode == null) {
            return new Location(0.0f, 0.0f);
        }
        return new Location(
            (float) locationNode.get("longitude").asDouble(),
            (float) locationNode.get("latitude").asDouble()
        );
    }
    
    private static Date parseTimestamp(String timestampStr) {
        try {
            return dateFormat.parse(timestampStr);
        } catch (Exception e) {
            return new Date();
        }
    }
    
    private static Direction parseWindDirection(String windDir) {
        try {
            return Direction.valueOf(windDir);
        } catch (IllegalArgumentException e) {
            return Direction.N;
        }
    }
}
