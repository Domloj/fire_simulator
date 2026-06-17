package pl.edu.agh.kis.firebackend.service.model.events;

import java.util.Map;

/**
 * Model for LLM Chat messages (requests from agents and responses from strategic LLM).
 */
public record EvLlmChat(
    String agentId,
    String type,
    String action,
    Integer sectorId,
    Integer priority,
    String description,
    Map<String, Double> location,
    String timestamp,
    String status,
    Object content,
    String source
) { }
