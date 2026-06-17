package pl.edu.agh.kis.firebackend.configuration;

import java.util.HashMap;
import java.util.Map;

/**
 * Maps queue names to routing keys for RabbitMQ topic exchange.
 * Routing keys use dots (.) while queue names use underscores (_).
 */
public class RoutingKeys {
    
    private static final Map<String, String> QUEUE_TO_ROUTING_KEY = new HashMap<>();
    private static final Map<String, String> ROUTING_KEY_TO_QUEUE = new HashMap<>();
    
    static {        
        // Simulation 
        map(QueueNames.SIMULATION_TELEMETRY_AGENTS_FIRE_BRIGADE,     "simulation.telemetry.agents.fire_brigade");
        map(QueueNames.SIMULATION_TELEMETRY_AGENTS_FIRE_BRIGADE_BATCH, "simulation.telemetry.agents.fire_brigade_batch");
        map(QueueNames.SIMULATION_TELEMETRY_AGENTS_FORESTER,         "simulation.telemetry.agents.forester");
        map(QueueNames.SIMULATION_TELEMETRY_AGENTS_FORESTER_BATCH,   "simulation.telemetry.agents.forester_batch");
        map(QueueNames.SIMULATION_TELEMETRY_MAP_SECTOR_STATE,        "simulation.telemetry.map.sector_state");
        map(QueueNames.SIMULATION_TELEMETRY_MAP_SECTOR_STATE_FAST,   "simulation.telemetry.map.sector_state_fast");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_TEMP_HUMIDITY,   "simulation.telemetry.sensors.temp_humidity");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_WIND_SPEED,      "simulation.telemetry.sensors.wind_speed");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_WIND_DIRECTION,  "simulation.telemetry.sensors.wind_direction");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_LITTER_MOISTURE, "simulation.telemetry.sensors.litter_moisture");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_CO2,             "simulation.telemetry.sensors.co2");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_PM2_5,           "simulation.telemetry.sensors.pm2_5");
        map(QueueNames.SIMULATION_TELEMETRY_SENSORS_CAMERA,             "simulation.telemetry.sensors.camera");

        // Support System
        map(QueueNames.SUPPORT_ANALYSIS_REQUESTS,  "support.analysis.requests");
        map(QueueNames.SUPPORT_RECOMMENDATIONS,    "support.recommendations");
        map(QueueNames.SUPPORT_AGGREGATED_DATA,    "support.data.aggregated");
        
        // Simulation Recommendations
        map(QueueNames.SIMULATION_RECOMMENDATIONS, "simulation.recommendations");
        map(QueueNames.BACKEND_LLM_REQUESTS,       "support.llm.requests");
        map(QueueNames.BACKEND_LLM_RESPONSES,      "support.llm.responses");
        map(QueueNames.SUPPORT_LLM_PROPOSITIONS,   "support.llm.propositions");
        map(QueueNames.SUPPORT_LLM_PROPOSITIONS_RESPONSES, "support.llm.propositions.responses");
        map(QueueNames.SUPPORT_LLM_REQUESTS,       "support.llm.requests");
        map(QueueNames.SUPPORT_LLM_RESPONSES,      "support.llm.responses");
        map(QueueNames.SUPPORT_ANALYTICS_INSIGHTS, "support.analytics.insights");
        
        // Backend Orchestration
        map(QueueNames.BACKEND_TASKS_QUEUE,     "backend.tasks.queue");
        map(QueueNames.BACKEND_DATA_AGGREGATED, "backend.data.aggregated");
        map(QueueNames.BACKEND_COMMANDS_USER,   "backend.commands.user");

        // Control (will be used instead of REST API)
        map(QueueNames.SIMULATION_CONTROL_FIRE_BRIGADE_ACTIONS, "simulation.control.fire_brigade_actions");
        map(QueueNames.SIMULATION_CONTROL_FORESTER_ACTIONS,     "simulation.control.forester_actions");
        map(QueueNames.SIMULATION_CONTROL_LIFECYCLE,            "simulation.control.lifecycle");
    }
    
    private static void map(String queueName, String routingKey) {
        QUEUE_TO_ROUTING_KEY.put(queueName, routingKey);
        ROUTING_KEY_TO_QUEUE.put(routingKey, queueName);
    }
    
    /**
     * Get routing key for a given queue name.
     * @param queueName Queue name with underscores
     * @return Routing key with dots, or queueName if not mapped
     */
    public static String getRoutingKey(String queueName) {
        return QUEUE_TO_ROUTING_KEY.getOrDefault(queueName, queueName);
    }
    
    /**
     * Get queue name for a given routing key.
     * @param routingKey Routing key with dots
     * @return Queue name with underscores, or routingKey if not mapped
     */
    public static String getQueueName(String routingKey) {
        return ROUTING_KEY_TO_QUEUE.getOrDefault(routingKey, routingKey.replace('.', '_'));
    }
    
    private RoutingKeys() {
        // Utility class - prevent instantiation
    }
}
