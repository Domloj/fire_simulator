package pl.edu.agh.kis.firebackend.service.model.simulation;

import pl.edu.agh.kis.firebackend.service.model.FireBrigadeAction;
import pl.edu.agh.kis.firebackend.service.model.FireBrigadeState;
import pl.edu.agh.kis.firebackend.service.model.configuration.ConfFireBrigade;
import pl.edu.agh.kis.firebackend.model.events.EvFireBrigade;
import pl.edu.agh.kis.firebackend.model.primitives.Location;

public record FireBrigade(
    int fireBrigadeId,
    int sectorId,
    Location location,
    FireBrigadeState state,
    FireBrigadeAction action
) {

    /**
     * Zwraca kopię obiektu bez pola location (do wysyłki w pełnym stanie)
     */
    public FireBrigade withoutLocation() {
        return new FireBrigade(
            this.fireBrigadeId(),
            this.sectorId(),
            null, // location usuwamy
            this.state(),
            this.action()
        );
    }
    public static FireBrigade from(ConfFireBrigade confFireBrigade) 
    {
        return new FireBrigade(
                confFireBrigade.fireBrigadeId(),
                0,
                confFireBrigade.currentLocation(),
                confFireBrigade.state(),
                FireBrigadeAction.EXTINGUISH
        );
    }

    public static FireBrigade from(EvFireBrigade evFireBrigade) 
    {
        return new FireBrigade(
                evFireBrigade.fireBrigadeId(),
                evFireBrigade.sectorId() != null ? evFireBrigade.sectorId() : 0,
                evFireBrigade.location(),
                evFireBrigade.state(),
                FireBrigadeAction.EXTINGUISH
        );
    }
}
