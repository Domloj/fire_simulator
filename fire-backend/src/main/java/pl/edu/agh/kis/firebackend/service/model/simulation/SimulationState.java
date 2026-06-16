package pl.edu.agh.kis.firebackend.service.model.simulation;

import lombok.AllArgsConstructor;
import pl.edu.agh.kis.firebackend.service.model.configuration.Configuration;

import pl.edu.agh.kis.firebackend.model.events.RecommendedAction;

import java.util.*;
import java.util.stream.Collectors;

public class SimulationState {
    public String forestName;
    public Date timestamp;
    public long tick;
    public Map<Integer, Sector> sectors;
    public Map<Integer, FireBrigade> fireBrigades;
    public Map<Integer, ForesterPatrol> foresterPatrols;
    // Keyed by composite key "unitType:unitId" to avoid ID clashes between unit types
    public Map<String, RecommendedAction> recommendedActions; 

    public SimulationState(String forestName, Date timestamp, long tick, Map<Integer, Sector> sectors, Map<Integer, FireBrigade> fireBrigades, Map<Integer, ForesterPatrol> foresterPatrols, Map<String, RecommendedAction> recommendedActions) {
        this.forestName = forestName;
        this.timestamp = timestamp;
        this.tick = tick;
        this.sectors = sectors;
        this.fireBrigades = fireBrigades;
        this.foresterPatrols = foresterPatrols;
        this.recommendedActions = recommendedActions;
    }

    public SimulationState() {
        this.forestName = "";
        this.timestamp = new Date();
        this.tick = 0L;
        this.sectors = new HashMap<>();
        this.fireBrigades = new HashMap<>();
        this.foresterPatrols = new HashMap<>();
        this.recommendedActions = new HashMap<>();  
        // this.foresterPatrols.put(1, new ForesterPatrol(1, new Date(), ForesterPatrolState.PATROLLING, new Location(1.0, 1.0), new Location(12.0, 12.0)));
    }

    public static SimulationState from(Configuration configuration) {
        Map<Integer, Sector> sectors = configuration
                .sectors()
                .stream()
                .collect(Collectors.toMap(sector -> sector.sectorId(), Sector::from));
        
        Map<Integer, FireBrigade>  fireBrigades = configuration
                .fireBrigades()
                .stream()
                .collect(Collectors.toMap(fireBrigade -> fireBrigade.fireBrigadeId(), FireBrigade::from));
        
        Map<Integer, ForesterPatrol> foresterPatrols = configuration
                .foresterPatrols()
                .stream()
                .collect(Collectors.toMap(foresterPatrol -> foresterPatrol.foresterPatrolId(), ForesterPatrol::from));
        
        Map<String, RecommendedAction> recommendedActions = new HashMap<>(); 
        
        return new SimulationState(
                configuration.forestName(),
                new Date(),
                0L,
                sectors,
                fireBrigades,
                foresterPatrols,
                recommendedActions
        );
    }
}
