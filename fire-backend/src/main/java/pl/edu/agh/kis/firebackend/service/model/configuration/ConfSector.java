package pl.edu.agh.kis.firebackend.service.model.configuration;

import pl.edu.agh.kis.firebackend.service.model.SectorState;

import java.util.List;

public record ConfSector(
    int sectorId,
    int row,
    int column,
    SectorState initialState,
    SectorType sectorType,
    List<List<Double>> contours,
    List<Integer> assignedBrigades
) {
}
