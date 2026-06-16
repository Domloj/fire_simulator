package pl.edu.agh.kis.firebackend.configuration;

/**
 * Centralized queue names with proper prefixes.
 * All queue names should use underscores and proper prefixes:
 * - simulation_* for simulation-related queues
 * - support_* for support system queues
 * - backend_* for backend orchestration queues
 */
public class QueueNames {

    // Simulation Control (commands TO simulator)
    // TODO: NOT USED
    public static final String SIMULATION_CONTROL_FIRE_BRIGADE_ACTIONS = "simulation_control_fire_brigade_actions";
    public static final String SIMULATION_CONTROL_FORESTER_ACTIONS = "simulation_control_forester_actions";
    public static final String SIMULATION_CONTROL_LIFECYCLE = "simulation_control_lifecycle";

    /**
     * Simulation Telemetry (data FROM simulator)
     * All the parameters used by simulation system.
     */
    public static final String SIMULATION_TELEMETRY_AGENTS_FIRE_BRIGADE = "simulation_telemetry_agents_fire_brigade";
    public static final String SIMULATION_TELEMETRY_AGENTS_FIRE_BRIGADE_BATCH = "simulation_telemetry_agents_fire_brigade_batch";
    public static final String SIMULATION_TELEMETRY_AGENTS_FORESTER = "simulation_telemetry_agents_forester";
    public static final String SIMULATION_TELEMETRY_AGENTS_FORESTER_BATCH = "simulation_telemetry_agents_forester_batch";
    public static final String SIMULATION_TELEMETRY_MAP_SECTOR_STATE = "simulation_telemetry_map_sector_state";
    public static final String SIMULATION_TELEMETRY_MAP_SECTOR_STATE_FAST = "simulation_telemetry_map_sector_state_fast";
    public static final String SIMULATION_TELEMETRY_SENSORS_TEMP_HUMIDITY = "simulation_telemetry_sensors_temp_humidity";
    public static final String SIMULATION_TELEMETRY_SENSORS_WIND_SPEED = "simulation_telemetry_sensors_wind_speed";
    public static final String SIMULATION_TELEMETRY_SENSORS_WIND_DIRECTION = "simulation_telemetry_sensors_wind_direction";
    public static final String SIMULATION_TELEMETRY_SENSORS_LITTER_MOISTURE = "simulation_telemetry_sensors_litter_moisture";
    public static final String SIMULATION_TELEMETRY_SENSORS_CO2 = "simulation_telemetry_sensors_co2";
    public static final String SIMULATION_TELEMETRY_SENSORS_PM2_5 = "simulation_telemetry_sensors_pm2_5";
    public static final String SIMULATION_TELEMETRY_SENSORS_CAMERA = "simulation_telemetry_sensors_camera";

    // Support System
    public static final String SUPPORT_ANALYSIS_REQUESTS = "support_analysis_requests";
    public static final String SUPPORT_RECOMMENDATIONS = "support_recommendations";
    public static final String SUPPORT_AGGREGATED_DATA = "support_data_aggregated";

    // Simulation Recommendations (from simulation to backend)
    public static final String SIMULATION_RECOMMENDATIONS = "simulation_recommendations";
    public static final String BACKEND_LLM_REQUESTS = "backend_llm_requests";
    public static final String BACKEND_LLM_RESPONSES = "backend_llm_responses";
    public static final String SUPPORT_LLM_PROPOSITIONS = "support_llm_propositions";
    public static final String SUPPORT_LLM_PROPOSITIONS_RESPONSES = "support_llm_propositions_responses";
    public static final String SUPPORT_LLM_REQUESTS = "support_llm_requests";
    public static final String SUPPORT_LLM_RESPONSES = "support_llm_responses";
    public static final String SUPPORT_ANALYTICS_INSIGHTS = "support_analytics_insights";

    // Backend Orchestration
    public static final String BACKEND_TASKS_QUEUE = "backend_tasks_queue";
    public static final String BACKEND_DATA_AGGREGATED = "backend_data_aggregated";
    public static final String BACKEND_COMMANDS_USER = "backend_commands_user";

    private QueueNames() {
        // Utility class - prevent instantiation
    }
}
