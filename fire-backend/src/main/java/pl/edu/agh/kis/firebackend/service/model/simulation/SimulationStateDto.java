package pl.edu.agh.kis.firebackend.service.model.simulation;

import pl.edu.agh.kis.firebackend.model.events.EvRecommendation;
import pl.edu.agh.kis.firebackend.model.events.RecommendedAction;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public record SimulationStateDto (
    String forestName,
    Date timestamp,
    long tick,
    List<Sector> sectors,
    /**
     * Lista brygad straży pożarnej (BEZ pola location, pozycje tylko przez agent_position!)
     * Deprecated: location nie jest już wysyłane w pełnym stanie.
     */
    List<FireBrigade> fireBrigades,
    /**
     * Lista patroli leśnych (BEZ pola location, pozycje tylko przez agent_position!)
     * Deprecated: location nie jest już wysyłane w pełnym stanie.
     */
    List<ForesterPatrol> foresterPatrols,
    List<RecommendedAction> recommendedActions
){
    public static SimulationStateDto from(SimulationState state) {
        // Location zostaje w pełnym stanie — frontend (AgentPositionController)
        // rysuje pozycje agentów z data.fireBrigades/foresterPatrols. Dedykowany
        // kanał agent_position nie dostarczał pozycji, a dane ruchu i tak są
        // w pełnym stanie co tick, więc po prostu ich nie wycinamy.
        return new SimulationStateDto(
            state.forestName,
            state.timestamp,
            state.tick,
            new ArrayList<>(state.sectors.values()),
            new ArrayList<>(state.fireBrigades.values()),
            new ArrayList<>(state.foresterPatrols.values()),
            new ArrayList<>(state.recommendedActions.values())
        );
    }

//    public static SimulationState fromConfiguration(Configuration configuration) {
//        return new SimulationState(
//                configuration.forestName(),
//                new Date(),
//                configuration.sectors().stream().map(Sector::fromConfig).toList()
//        );
//    }
}
