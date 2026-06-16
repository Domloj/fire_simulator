package pl.edu.agh.kis.firebackend.configuration;

import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import pl.edu.agh.kis.firebackend.service.model.UpdatesQueue;
import pl.edu.agh.kis.firebackend.model.events.*;
import pl.edu.agh.kis.firebackend.service.StateUpdatesService;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import static pl.edu.agh.kis.firebackend.configuration.QueueNames.*;

@Configuration
@RequiredArgsConstructor
public class DeclaredQueues {
    private final StateUpdatesService stateUpdatesService;

    private <T> Flux<T> createFlux(String queueName, Class<T> clazz) {
        return stateUpdatesService.createUpdatesFlux(new UpdatesQueue<>(queueName, clazz));
    }

    /**
     * Simulation Telemetry (data FROM simulator)
     * All the parameters used by simulation system.
     */
    @Bean
    public Flux<EvFireBrigade> fireBrigadeUpdates() {
        return createFlux(SIMULATION_TELEMETRY_AGENTS_FIRE_BRIGADE, EvFireBrigade.class);
    }

    @Bean
    public Flux<EvFireBrigadeBatch> fireBrigadeBatchUpdates() {
        return createFlux(SIMULATION_TELEMETRY_AGENTS_FIRE_BRIGADE_BATCH, EvFireBrigadeBatch.class);
    }

    @Bean
    public Flux<EvForestPatrol> foresterPatrolUpdates() {
        return createFlux(SIMULATION_TELEMETRY_AGENTS_FORESTER, EvForestPatrol.class);
    }

    @Bean
    public Flux<EvForesterPatrolBatch> foresterPatrolBatchUpdates() {
        return createFlux(SIMULATION_TELEMETRY_AGENTS_FORESTER_BATCH, EvForesterPatrolBatch.class);
    }

    @Bean
    public Flux<EvWindSpeedSensor> windSpeedSensorUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_WIND_SPEED, EvWindSpeedSensor.class);
    }

    @Bean
    public Flux<EvTempAndAirHumiditySensor> tempAndAirHumiditySensorUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_TEMP_HUMIDITY, EvTempAndAirHumiditySensor.class);
    }

    @Bean
    public Flux<EvWindDirectionSensor> windDirectionSensorUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_WIND_DIRECTION, EvWindDirectionSensor.class);
    }

    @Bean
    public Flux<EvLitterMoistureSensor> litterMoistureSensorUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_LITTER_MOISTURE, EvLitterMoistureSensor.class);
    }

    @Bean
    public Flux<EvCO2Sensor> co2SensorUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_CO2, EvCO2Sensor.class);
    }

    @Bean
    public Flux<EvPM25ConcentrationSensor> pm25ConcentrationSensorUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_PM2_5, EvPM25ConcentrationSensor.class);
    }

    @Bean
    public Flux<EvCamera> cameraUpdates() {
        return createFlux(SIMULATION_TELEMETRY_SENSORS_CAMERA, EvCamera.class);
    }

    @Bean
    public Flux<EvSectorState> simulationState() {
        return createFlux(SIMULATION_TELEMETRY_MAP_SECTOR_STATE, EvSectorState.class);
    }

    @Bean
    public Flux<EvSectorState> simulationStateFast() {
        return createFlux(SIMULATION_TELEMETRY_MAP_SECTOR_STATE_FAST, EvSectorState.class);
    }

    /**
     * Support System
     * This at least should use different data type, tailored for support system,
     * BUT im not sure if it's worth the effort. Using the same data type for now.
     * TODO: Consider using different data type.
     */
    @Bean
    public Flux<EvSectorState> supportAnalysisRequests() {
        return createFlux(SUPPORT_ANALYSIS_REQUESTS, EvSectorState.class);
    }

    @Bean
    public Flux<EvRecommendation> recommendationUpdates() {
        // Merge recommendations coming from support system and (optionally) from simulation.
        // IMPORTANT:
        //  - Backend NEVER auto-executes these recommendations.
        //  - They are only forwarded to frontend (via SSE) so that UI
        //    can decide whether to apply them (auto-apply toggle / manual APPLY).
        Flux<EvRecommendation> supportRecommendations = createFlux(SUPPORT_RECOMMENDATIONS, EvRecommendation.class);
        Flux<EvRecommendation> simulationRecommendations = createFlux(SIMULATION_RECOMMENDATIONS,
                EvRecommendation.class);
        return Flux.merge(supportRecommendations, simulationRecommendations);
    }

    @Bean
    public Flux<EvSectorState> supportDataAggregated() {
        return createFlux(SUPPORT_AGGREGATED_DATA, EvSectorState.class);
    }

    /**
     * NOT USED
     * When designing the support this queues were considered, but due to
     * short time, they were not implemented.
     * 
     * The idea was to have separate queues for LLM requests and responses
     * for communication of FIRE / FORESTER -> SUPPORT and SUPPORT -> FIRE /
     * FORESTER
     */
    @Bean
    public Flux<EvLlmChat> supportLLMRequests() {
        return createFlux(BACKEND_LLM_REQUESTS, EvLlmChat.class);
    }

    @Bean
    public Flux<EvLlmChat> supportLLMResponses() {
        return createFlux(BACKEND_LLM_RESPONSES, EvLlmChat.class);
    }

    @Bean
    public Flux<EvLlmChat> supportLLMPropositions() {
        return createFlux(SUPPORT_LLM_PROPOSITIONS, EvLlmChat.class);
    }

    @Bean
    public Flux<EvLlmChat> supportLLMPropositionsResponses() {
        return createFlux(SUPPORT_LLM_PROPOSITIONS_RESPONSES, EvLlmChat.class);
    }

    /**
     * Shared Sink for LLM Chat messages
     * Used both by SimulationStateService and llmChatSink Bean
     */
    @Bean("llmChatSinkShared")
    public Sinks.Many<EvLlmChat> llmChatSinkShared() {
        return Sinks.many().multicast().onBackpressureBuffer();
    }

    /**
     * Aggregated LLM Chat Stream for Frontend
     * Combines all LLM communication: requests, responses, propositions, and
     * proposition responses
     */
    @Bean("llmChatSink")
    public Flux<EvLlmChat> llmChatSink(Sinks.Many<EvLlmChat> llmChatSinkShared) {
        Flux<EvLlmChat> requests = supportLLMRequests();
        Flux<EvLlmChat> responses = supportLLMResponses();
        Flux<EvLlmChat> propositions = supportLLMPropositions();
        Flux<EvLlmChat> propositionResponses = supportLLMPropositionsResponses();
        Flux<EvLlmChat> sharedSinkFlux = llmChatSinkShared.asFlux();

        return Flux.merge(requests, responses, propositions, propositionResponses, sharedSinkFlux)
                .share();
    }

    /**
     * Agent positions sink (high-frequency position-only messages).
     * Published by SimulationStateService when receiving agent telemetry.
     */
    @Bean("agentPositionSink")
    public Sinks.Many<Object> agentPositionSink() {
        return Sinks.many().multicast().onBackpressureBuffer();
    }

    @Bean
    public Flux<EvSectorState> supportAnalyticsInsights() {
        return createFlux(SUPPORT_ANALYTICS_INSIGHTS, EvSectorState.class);
    }
}
