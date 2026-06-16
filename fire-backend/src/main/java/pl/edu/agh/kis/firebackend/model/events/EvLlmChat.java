package pl.edu.agh.kis.firebackend.model.events;

public record EvLlmChat(
    String agentId,
    String type,
    String action,
    Integer sectorId,
    Integer priority,
    String description,
    String location,
    String timestamp,
    String status,
    String content,
    String source
) { }
