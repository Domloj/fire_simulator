package pl.edu.agh.kis.firebackend.service.model.simulation;

import lombok.AllArgsConstructor;
import pl.edu.agh.kis.firebackend.service.model.SectorState;
import pl.edu.agh.kis.firebackend.service.model.configuration.ConfSector;

import java.util.List;
import java.util.ArrayList;

public class Sector 
{
    public int sectorId;
    public SectorState state;
    public List<List<Double>> contours;
    public List<Integer> assignedBrigades;

    public Sector(int sectorId, SectorState state, List<List<Double>> contours, List<Integer> assignedBrigades) {
        this.sectorId = sectorId;
        this.state = state;
        this.contours = contours;
        this.assignedBrigades = assignedBrigades;
    }

    public static Sector from(ConfSector confSector) 
    {
        List<Integer> assigned = confSector.assignedBrigades();
        if (assigned == null) assigned = new ArrayList<>();
        return new Sector(confSector.sectorId(), confSector.initialState(), confSector.contours(), assigned);
    }
}
