package pl.edu.agh.kis.firebackend.service.model.simulation;

import pl.edu.agh.kis.firebackend.model.primitives.Location;
import pl.edu.agh.kis.firebackend.service.model.ForesterPatrolState;
import pl.edu.agh.kis.firebackend.service.model.ForesterPatrolAction;
import pl.edu.agh.kis.firebackend.model.events.EvForestPatrol;
import pl.edu.agh.kis.firebackend.service.model.configuration.ConfForesterPatrol;

public record ForesterPatrol(
    int foresterPatrolId,
    int sectorId,
    Location location,
    ForesterPatrolState state,
    ForesterPatrolAction action
) {

    public ForesterPatrol withoutLocation() {
        return new ForesterPatrol(
            this.foresterPatrolId(),
            this.sectorId(),
            null,
            this.state(),
            this.action()
        );
    }

    public static ForesterPatrol from(ConfForesterPatrol confForesterPatrol) {
        return new ForesterPatrol(
                confForesterPatrol.foresterPatrolId(),
                0,
                confForesterPatrol.currentLocation(),
                confForesterPatrol.state(),
                ForesterPatrolAction.PATROL
        );
    }

    public static ForesterPatrol from(EvForestPatrol evForestPatrol) {
        return new ForesterPatrol(
                evForestPatrol.foresterPatrolId(),
                evForestPatrol.sectorId() != null ? evForestPatrol.sectorId() : 0,
                evForestPatrol.location(),
                evForestPatrol.state(),
                ForesterPatrolAction.PATROL
        );
    }
}


