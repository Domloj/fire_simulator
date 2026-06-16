package pl.edu.agh.kis.firebackend.controller;

import lombok.RequiredArgsConstructor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import pl.edu.agh.kis.firebackend.service.model.configuration.Configuration;
import pl.edu.agh.kis.firebackend.model.events.EvLlmChat;
import pl.edu.agh.kis.firebackend.service.HttpRequestService;
import pl.edu.agh.kis.firebackend.service.SimulationStateService;
import pl.edu.agh.kis.firebackend.service.StateUpdatesService;
import pl.edu.agh.kis.firebackend.configuration.QueueNames;
import org.springframework.context.ApplicationContext;
import reactor.core.publisher.Flux;

import java.time.Duration;

@RestController
@RequiredArgsConstructor
@CrossOrigin(origins = "*")
@RequestMapping("/simulation")
public class SimulationStateController 
{
    private final SimulationStateService simulationStateService;
    private final HttpRequestService httpRequestService;
    private final StateUpdatesService stateUpdatesService;
    private final ApplicationContext applicationContext;
    
    private static final Logger log = LoggerFactory.getLogger(SimulationStateController.class);

    @Value("${FIRE_SIMULATION_SERVICE:127.0.0.1}")
    private String simulationHost;

    @Value("${SIMULATOR_PORT:5000}")
    private int simulatorPort;

    @Value("${FIRE_SUPPORT_SERVICE:127.0.0.1}")
    private String supportHost;

    @Value("${SUPPORT_PORT:5001}")
    private int supportPort;

    @PostMapping(value = "/run-simulation", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Object> runSimulation(
        @RequestParam(required = false) Long interval,
        @RequestParam(name = "llmMode", required = false, defaultValue = "false") boolean llmMode,
        @RequestBody Configuration configuration)
    {
        // Hard limit: at most ~1 update per second (every 1000ms) to protect
        // simulation and frontend from excessive update frequency, but still keep
        // agents visually smooth on the map.
        // If the frontend requests a lower interval, we clamp it up to 1000ms.
        long effectiveIntervalMs = (interval != null && interval > 0) ? Math.max(interval, 1000L) : 1000L;

        if (interval != null && interval < effectiveIntervalMs) {
            log.info("Requested simulation interval {} ms is below minimum; clamping to {} ms", interval, effectiveIntervalMs);
        }

        try {
            String supportUrl = String.format("http://%s:%d/start", supportHost, supportPort);

            java.util.Map<String, Object> payload = new java.util.HashMap<>();
            payload.put("config", configuration);

            if (llmMode) {
                java.util.Map<String, Object> llmConfig = new java.util.HashMap<>();
                // Pure LLM-driven recommendations (no MCTS)
                llmConfig.put("recommendation_mode", "llm");
                // Decisions po stronie agentów domyślnie heurystyczne – centralny LLM w support
                llmConfig.put("agent_decision_mode", "heuristic");
                // Włącz koordynację LLM i komunikację agentów w support
                llmConfig.put("enable_llm_coordination", true);
                llmConfig.put("enable_agent_communication", true);
                payload.put("llm_config", llmConfig);

                log.info("Starting support service in LLM-DRIVEN mode (recommendation_mode=llm)");
            } else {
                log.info("Starting support service in default mode (LLM configuration from env/.env)");
            }

            httpRequestService.sendPostRequest(supportUrl, payload);
        } catch (Exception e) {
            log.warn("Failed to start support service at {}:{} - continuing without support", supportHost, supportPort, e);
        }

        return simulationStateService.runSimulation(configuration, Duration.ofMillis(effectiveIntervalMs));
    }

    @GetMapping(
        value = "/llm-chat",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<EvLlmChat> streamLlmChat() {
        log.info("Frontend connected to LLM chat stream");
        @SuppressWarnings("unchecked")
        Flux<EvLlmChat> llmChatSink = applicationContext.getBean("llmChatSink", Flux.class);
        return llmChatSink
            .doOnSubscribe(s -> log.debug("LLM chat stream subscribed"))
            .doOnTerminate(() -> log.debug("LLM chat stream terminated"))
            .timeout(Duration.ofMinutes(30));
    }

    @PostMapping("/send-simulation-request")
    public ResponseEntity<String> sendSimulationRequest(@RequestBody Configuration configuration)
    {
        // Support startujemy zanim symulator dostanie config — inaczej support
        // przegapi konfigurację publikowaną na starcie symulacji.
        try {
            String supportUrl = String.format("http://%s:%d/start", supportHost, supportPort);
            java.util.Map<String, Object> payload = new java.util.HashMap<>();
            payload.put("config", configuration);
            log.info("Starting support service at {}:{} before simulation", supportHost, supportPort);
            httpRequestService.sendPostRequest(supportUrl, payload);
        } catch (Exception e) {
            log.warn("Failed to start support service at {}:{} - continuing without support", supportHost, supportPort, e);
        }

        String url = String.format("http://%s:%d/run_simulation", simulationHost, simulatorPort);
        try {
            httpRequestService.sendPostRequest(url, configuration);
            return ResponseEntity.ok("Configuration sent to simulation!");
        } catch (Exception e) {
            log.error("Failed to send run_simulation request to simulation at {}:{}", simulationHost, simulatorPort, e);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation service unreachable");
        }
    }

    @GetMapping("/snapshot")
    public ResponseEntity<String> getSimulationSnapshot() {
        String url = String.format("http://%s:%d/snapshot", simulationHost, simulatorPort);
        try {
            String body = httpRequestService.sendGetRequest(url);
            return ResponseEntity.ok(body);
        } catch (Exception e) {
            log.error("Failed to fetch snapshot from simulation at {}:{}", simulationHost, simulatorPort, e);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation service unreachable");
        }
    }

    @PostMapping("/orderFireBrigade")
    public ResponseEntity<String> orderFireBrigade(@RequestBody Object payload) 
    {
        String url = String.format("http://%s:%d/orderFireBrigade", simulationHost, simulatorPort);
        try {
            log.info("Forwarding fire brigade order to simulation at {}:{} payload={}", simulationHost, simulatorPort, payload);
            httpRequestService.sendPostRequest(url, payload);
            log.debug("Fire brigade order successfully forwarded to simulation");
            return ResponseEntity.ok("Order forwarded to simulation");
        } catch (Exception e) {
            log.warn("Failed to forward fire brigade order to simulation at {}:{} - attempting queue fallback", simulationHost, simulatorPort);
            try {
                stateUpdatesService.sendMessageToQueue(QueueNames.SIMULATION_CONTROL_FIRE_BRIGADE_ACTIONS, payload)
                    .subscribe(
                        unused -> {},
                        err -> log.error("Fallback enqueue failed: {}", err.toString())
                    );
                return ResponseEntity.status(HttpStatus.ACCEPTED).body("Simulation unreachable; order queued");
            } catch (Exception ex) {
                log.error("Fallback enqueue failed entirely: {}", ex.toString());
                return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation unreachable and enqueue failed");
            }
        }
    }

    @PostMapping("/orderForestPatrol")
    public ResponseEntity<String> orderForestPatrol(@RequestBody Object payload) 
    {
        String url = String.format("http://%s:%d/orderForestPatrol", simulationHost, simulatorPort);
        try {
            log.info("Forwarding forester patrol order to simulation at {}:{} payload={}", simulationHost, simulatorPort, payload);
            httpRequestService.sendPostRequest(url, payload);
            log.debug("Forester patrol order successfully forwarded to simulation");
            return ResponseEntity.ok("Order forwarded to simulation");
        } catch (Exception e) {
            log.warn("Failed to forward forester patrol order to simulation at {}:{} - attempting queue fallback", simulationHost, simulatorPort);
            try {
                stateUpdatesService.sendMessageToQueue(QueueNames.SIMULATION_CONTROL_FORESTER_ACTIONS, payload)
                    .subscribe(
                        unused -> {},
                        err -> log.error("Fallback enqueue failed: {}", err.toString())
                    );
                return ResponseEntity.status(HttpStatus.ACCEPTED).body("Simulation unreachable; order queued");
            } catch (Exception ex) {
                log.error("Fallback enqueue failed entirely: {}", ex.toString());
                return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation unreachable and enqueue failed");
            }
        }
    }

    @PostMapping("/assignBrigades")
    public ResponseEntity<String> assignBrigades(@RequestBody java.util.Map<String, Object> payload) 
    {
        Object sectorIdObj = payload.get("sectorId");
        Object assigned = payload.get("assignedBrigades");

        if (sectorIdObj instanceof Number) {
            int sectorId = ((Number) sectorIdObj).intValue();
            java.util.List<Integer> brigades = new java.util.ArrayList<>();

            if (assigned instanceof java.util.List<?>) 
                {
                for (Object o : (java.util.List<?>) assigned) 
                    {
                    if (o instanceof Number)
                    { 
                        brigades.add(((Number) o).intValue());
                    }
                    else if (o instanceof String) 
                    {
                        try { brigades.add(Integer.parseInt((String) o)); } catch (NumberFormatException e) { }
                    }
                }
            }
            simulationStateService.assignBrigadesToSector(sectorId, brigades);
        } 
        else
        {
            log.warn("Invalid sectorId in assignBrigades payload: {}", sectorIdObj);
        }

        String url = String.format("http://%s:%d/assignBrigades", simulationHost, simulatorPort);
        try {
            httpRequestService.sendPostRequest(url, payload);
            return ResponseEntity.ok("AssignBrigades forwarded to simulation");
        } catch (Exception e) {
            log.error("Failed to forward assignBrigades to simulation at {}:{}", simulationHost, simulatorPort, e);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation service unreachable");
        }
    }

    @PostMapping("/stop-simulation")
    public ResponseEntity<String> sendStopRequest() 
    {
        String url = String.format("http://%s:%d/stop_simulation", simulationHost, simulatorPort);
        try {
            httpRequestService.sendPostRequest(url, "");
            // Stop support service (best-effort)
            try {
                String supportUrl = String.format("http://%s:%d/stop", supportHost, supportPort);
                httpRequestService.sendPostRequest(supportUrl, "");
            } catch (Exception e) {
                log.warn("Failed to stop support service at {}:{} - continuing", supportHost, supportPort);
            }
            return ResponseEntity.ok("Stop request sent!");
        } catch (Exception e) {
            log.error("Failed to send stop_simulation request to simulation at {}:{}", simulationHost, simulatorPort, e);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation service unreachable");
        }
    }

    /**
     * Runtime toggle for LLM-driven recommendation mode in support service.
     *
     * Body example:
     * { "enabled": true }
     *
     * When enabled=true:
     *  - recommendation_mode = "llm"
     *  - agent_decision_mode = "heuristic"
     *  - enable_llm_coordination / enable_agent_communication = true
     *
     * When enabled=false:
     *  - recommendation_mode / agent_decision_mode left to defaults (env/.env)
     *    but LLM features are explicitly disabled.
     */
    @PostMapping("/llm-mode")
    public ResponseEntity<String> setLlmMode(@RequestBody java.util.Map<String, Object> body) {
        Object enabledObj = body.get("enabled");
        boolean enabled = Boolean.TRUE.equals(enabledObj) ||
                (enabledObj instanceof String && "true".equalsIgnoreCase((String) enabledObj));

        String supportUrl = String.format("http://%s:%d/config", supportHost, supportPort);

        java.util.Map<String, Object> llmConfig = new java.util.HashMap<>();

        if (enabled) {
            llmConfig.put("recommendation_mode", "llm");
            llmConfig.put("agent_decision_mode", "heuristic");
            llmConfig.put("enable_llm_coordination", true);
            llmConfig.put("enable_agent_communication", true);
            log.info("Enabling LLM-DRIVEN mode in support service (recommendation_mode=llm)");
        } else {
            // Turn off all LLM-driven behaviour in support
            llmConfig.put("recommendation_mode", "heuristic");
            llmConfig.put("agent_decision_mode", "heuristic");
            llmConfig.put("enable_llm_coordination", false);
            llmConfig.put("enable_agent_communication", false);
            log.info("Disabling LLM-DRIVEN mode in support service (fallback to heuristic)");
        }

        try {
            httpRequestService.sendPostRequest(supportUrl, llmConfig);
            return ResponseEntity.ok(enabled ? "LLM mode enabled" : "LLM mode disabled");
        } catch (Exception e) {
            log.error("Failed to update LLM mode in support service at {}:{}", supportHost, supportPort, e);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("Support service unreachable");
        }
    }

    @PostMapping("/set-speed")
    public ResponseEntity<String> setSimulationSpeed(@RequestParam("tickInterval") Double tickIntervalSeconds)
    {
        if (tickIntervalSeconds == null || tickIntervalSeconds <= 0) {
            return ResponseEntity.badRequest().body("tickInterval must be > 0");
        }

        String url = String.format("http://%s:%d/set_speed", simulationHost, simulatorPort);
        try {
            java.util.Map<String, Object> payload = java.util.Map.of("tickInterval", tickIntervalSeconds);
            httpRequestService.sendPostRequest(url, payload);
            return ResponseEntity.ok("Simulation speed updated");
        } catch (Exception e) {
            log.error("Failed to send set_speed request to simulation at {}:{}", simulationHost, simulatorPort, e);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("Simulation service unreachable");
        }
    }
}