package pl.edu.agh.kis.firebackend.service.model.frontend;

import java.util.List;
import pl.edu.agh.kis.firebackend.model.events.EvSectorState;

public record FrontSectorUpdateFast(
    String type,
    List<EvSectorState> sectors
) { }
