package pl.edu.agh.kis.firebackend.model.events;

import java.util.List;

public record EvRecommendation(
    float timestamp,
    List<RecommendedAction> recommendedActions,
    String priority
) { }
