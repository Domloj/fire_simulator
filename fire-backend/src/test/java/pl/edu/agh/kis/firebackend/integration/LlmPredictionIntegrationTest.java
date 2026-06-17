package pl.edu.agh.kis.firebackend.integration;

import org.junit.jupiter.api.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.*;
import org.springframework.test.context.TestPropertySource;
import org.springframework.web.client.RestTemplate;
import pl.edu.agh.kis.firebackend.configuration.QueueNames;
import pl.edu.agh.kis.firebackend.model.events.EvRecommendation;
import pl.edu.agh.kis.firebackend.service.StateUpdatesService;
import pl.edu.agh.kis.firebackend.service.model.UpdatesQueue;
import pl.edu.agh.kis.firebackend.service.model.configuration.Configuration;
import reactor.core.publisher.Flux;

import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Integration test for LLM prediction functionality across fire-backend, fire-simulation, and fire-support services.
 * 
 * This test verifies:
 * 1. Integration of LLM between all three services
 * 2. Generation of LLM predictions by support service
 * 3. Data flow: backend → simulation → support → backend (recommendations)
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestPropertySource(properties = {
    "RABBITMQ_HOST=127.0.0.1",
    "RABBITMQ_PORT=5672",
    "RABBITMQ_USER=guest",
    "RABBITMQ_PASS=guest",
    "MONGO_URI=mongodb://127.0.0.1:27017/configurations",
    "FIRE_SIMULATION_SERVICE=127.0.0.1",
    "FIRE_SUPPORT_SERVICE=127.0.0.1",
    "SIMULATOR_PORT=5000",
    "SUPPORT_PORT=5001"
})
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
@Tag("IntegrationTest")
public class LlmPredictionIntegrationTest {
    
    private static final Logger log = LoggerFactory.getLogger(LlmPredictionIntegrationTest.class);
    
    @LocalServerPort
    private int backendPort;
    
    @Autowired
    private StateUpdatesService stateUpdatesService;
    
    private RestTemplate httpClient;
    private String backendBaseUrl;
    private String simulationBaseUrl;
    private String supportBaseUrl;
    
    private Flux<EvRecommendation> recommendationsFlux;
    private List<EvRecommendation> receivedRecommendations;
    
    @BeforeEach
    void setUp() {
        httpClient = new RestTemplate();
        backendBaseUrl = "http://localhost:" + backendPort;
        simulationBaseUrl = "http://127.0.0.1:5000";
        supportBaseUrl = "http://127.0.0.1:5001";
        
        receivedRecommendations = new ArrayList<>();
        recommendationsFlux = stateUpdatesService.createUpdatesFlux(
            new UpdatesQueue<>(QueueNames.SUPPORT_RECOMMENDATIONS, EvRecommendation.class)
        );
        
        log.info("Test setup complete. Backend URL: {}", backendBaseUrl);
    }
    
    @AfterEach
    void tearDown() {
        try {
            httpClient.postForEntity(
                backendBaseUrl + "/simulation/stop-simulation",
                null,
                String.class
            );
            log.info("Stopped simulation");
        } catch (Exception e) {
            log.warn("Failed to stop simulation: {}", e.getMessage());
        }
        
        try {
            httpClient.postForEntity(
                supportBaseUrl + "/stop",
                null,
                String.class
            );
            log.info("Stopped support service");
        } catch (Exception e) {
            log.warn("Failed to stop support service: {}", e.getMessage());
        }
    }
    
    @Test
    @Order(1)
    @DisplayName("Test LLM prediction generation - full integration")
    void testLlmPredictionGeneration() throws IOException, InterruptedException {
        
        log.info("=== Starting LLM Prediction Integration Test ===");
        log.info("Backend URL: {}", backendBaseUrl);
        log.info("Simulation URL: {}", simulationBaseUrl);
        log.info("Support URL: {}", supportBaseUrl);
        
        log.info("Checking Fire Simulation service...");
        boolean simulationRunning = isServiceRunning(simulationBaseUrl);
        if (!simulationRunning) {
            log.error("  Fire Simulation service is NOT running!");
            log.error("  URL: {}/health", simulationBaseUrl);
            log.error("  Check: curl -v {}/health", simulationBaseUrl);
        } else {
            log.info("  Fire Simulation service is running");
            try {
                ResponseEntity<String> health = httpClient.getForEntity(simulationBaseUrl + "/health", String.class);
                log.info("  Health response: {}", health.getBody());
            } catch (Exception e) {
                log.warn("  Could not get health details: {}", e.getMessage());
            }
        }
        
        log.info("Checking Fire Support service...");
        boolean supportRunning = isServiceRunning(supportBaseUrl);
        if (!supportRunning) {
            log.error("  Fire Support service is NOT running!");
            log.error("  URL: {}/health", supportBaseUrl);
            log.error("  Check: curl -v {}/health", supportBaseUrl);
        } else {
            log.info("  Fire Support service is running");
            try {
                ResponseEntity<String> health = httpClient.getForEntity(supportBaseUrl + "/health", String.class);
                log.info("  Health response: {}", health.getBody());
            } catch (Exception e) {
                log.warn("  Could not get health details: {}", e.getMessage());
            }
        }

        assertTrue(simulationRunning, "Fire Simulation service should be running (sprawdź logi i endpoint /health)");
        assertTrue(supportRunning, "Fire Support service should be running (sprawdź logi i endpoint /health)");

        log.info("Configuring LLM mode...");
        configureLlmMode(true);
        
        // Verify LLM configuration
        try {
            ResponseEntity<Map> configResponse = httpClient.getForEntity(
                supportBaseUrl + "/config",
                Map.class
            );
            if (configResponse.getStatusCode().is2xxSuccessful() && configResponse.getBody() != null) {
                Map config = (Map) configResponse.getBody().get("config");
                log.info("Support service LLM config: {}", config);
            }
        } catch (Exception e) {
            log.warn("Could not verify LLM config: {}", e.getMessage());
        }

        log.info("Ładowanie konfiguracji lasu...");
        Path configPath = Paths.get("fire-configurations/forest/forest_5x5.json");
        Configuration config = TestUtils.loadForestConfig(configPath.toString());

        List<Integer> sectorsWithFire = Arrays.asList(1, 2, 3);
        config = TestUtils.addActiveFires(config, sectorsWithFire, 0.5);

        CountDownLatch recommendationLatch = new CountDownLatch(1);
        AtomicReference<EvRecommendation> firstRecommendation = new AtomicReference<>();

        log.info("Setting up recommendation listener...");
        recommendationsFlux
            .doOnNext(recommendation -> {
                int actionCount = recommendation.recommendedActions() != null ? recommendation.recommendedActions().size() : 0;
                log.info("  Received recommendation: {} actions, timestamp: {}", 
                    actionCount, recommendation.timestamp());
                
                if (actionCount > 0) {
                    recommendation.recommendedActions().forEach(action -> {
                        log.info("  - Action: unitId={}, sectorId={}, unitType={}", 
                            action.unitId(), action.sectorId(), action.unitType());
                    });
                }
                
                receivedRecommendations.add(recommendation);
                if (firstRecommendation.get() == null) {
                    firstRecommendation.set(recommendation);
                    recommendationLatch.countDown();
                }
            })
            .doOnError(error -> {
                log.error("  Error receiving recommendations: {}", error.getMessage(), error);
                recommendationLatch.countDown();
            })
            .doOnSubscribe(subscription -> {
                log.info("  Recommendation flux subscribed, waiting for messages...");
            })
            .subscribe();


        log.info("Starting simulation with LLM mode...");
        log.info("  Config: forestId={}, sectors={}, fireBrigades={}", 
            config.forestId(), config.sectors().size(), config.fireBrigades().size());
        
        ResponseEntity<String> runResponse;
        try {
            runResponse = httpClient.postForEntity(
                backendBaseUrl + "/simulation/run-simulation?llmMode=true",
                config,
                String.class
            );
            log.info("  Response status: {}", runResponse.getStatusCode());
            log.info("  Response body: {}", runResponse.getBody());
        } catch (Exception e) {
            log.error("  Failed to start simulation: {}", e.getMessage(), e);
            throw new AssertionError("Failed to start simulation: " + e.getMessage(), e);
        }

        if (runResponse.getStatusCode().is2xxSuccessful() || runResponse.getStatusCode() == HttpStatus.OK) {
            log.info("  Simulation start request successful (status: {})", runResponse.getStatusCode());
        } else {
            log.error("  Simulation start request failed (status: {})", runResponse.getStatusCode());
            log.error("  Response body: {}", runResponse.getBody());
        }
        assertTrue(
            runResponse.getStatusCode().is2xxSuccessful() || 
            runResponse.getStatusCode() == HttpStatus.OK,
            "Symulacja powinna uruchomić się poprawnie (HTTP)"
        );


        boolean simulationStarted = false;
        int timeoutSeconds = 20;
        for (int i = 0; i < timeoutSeconds; i++) {
            Thread.sleep(1000);
            if (isServiceRunning(simulationBaseUrl)) {
                simulationStarted = true;
                log.info("Symulacja faktycznie działa po uruchomieniu! (czekano {}s)", i+1);
                break;
            }
        }
        if (!simulationStarted) {
            log.error("Symulacja NIE wystartowała w ciągu {} sekund po żądaniu! Sprawdź backend i fire-simulation.", timeoutSeconds);
        }
        assertTrue(simulationStarted, "Symulacja powinna faktycznie działać po uruchomieniu (sprawdzenie /health, timeout " + timeoutSeconds + "s)");
        log.info("Symulacja uruchomiona, oczekiwanie na rekomendacje...");

        log.info("Waiting for recommendations (timeout: 30s)...");
        boolean recommendationReceived = recommendationLatch.await(30, TimeUnit.SECONDS);
        
        if (!recommendationReceived) {
            log.error("  No recommendation received within 30 seconds!");
            log.error("  Received recommendations count: {}", receivedRecommendations.size());
            log.error("  Check RabbitMQ queue: support.recommendations");
            log.error("  Check support service logs for errors");
        }
        
        assertTrue(recommendationReceived, 
            "Powinna zostać odebrana przynajmniej jedna rekomendacja w ciągu 30 sekund. " +
            "Odebrano: " + receivedRecommendations.size());
        assertFalse(receivedRecommendations.isEmpty(), 
            "Powinna zostać odebrana przynajmniej jedna rekomendacja. " +
            "Odebrano: " + receivedRecommendations.size());

        EvRecommendation recommendation = firstRecommendation.get();
        assertNotNull(recommendation, "Pierwsza rekomendacja nie powinna być nullem");
        
        log.info("Validating recommendation structure...");
        boolean validStructure = TestUtils.isValidRecommendationStructure(recommendation);
        if (!validStructure) {
            log.error("  Invalid recommendation structure!");
            log.error("  Recommendation: {}", recommendation);
        }
        assertTrue(validStructure, "Struktura rekomendacji powinna być poprawna");

        log.info("Checking if recommendation targets active fires...");
        boolean targetsFires = TestUtils.targetsActiveFires(recommendation, new HashSet<>(sectorsWithFire));
        if (!targetsFires) {
            log.warn("  Recommendation does not target active fire sectors");
            log.warn("  Expected sectors with fire: {}", sectorsWithFire);
            recommendation.recommendedActions().forEach(action -> {
                log.warn("  - Action targets sector: {}", action.sectorId());
            });
        }
        assertTrue(targetsFires,
            "Rekomendacja powinna dotyczyć sektorów z aktywnym pożarem. " +
            "Expected: " + sectorsWithFire);

        log.info("Checking if recommendation is from LLM...");
        boolean isLlm = TestUtils.isLlmRecommendation(recommendation);
        if (!isLlm) {
            log.warn("  Recommendation does not appear to be from LLM");
            log.warn("  This might be an MCTS recommendation instead");
        }
        assertTrue(isLlm, "Rekomendacja powinna pochodzić z LLM");

        log.info("=== Test completed successfully! ===");
        log.info("Total recommendations received: {}", receivedRecommendations.size());
    }
    
    /**
     * Configure LLM mode in support service via backend.
     */
    private void configureLlmMode(boolean enabled) {
        log.info("Configuring LLM mode: enabled={}", enabled);
        
        // First, configure via backend endpoint
        Map<String, Object> requestBody = new HashMap<>();
        requestBody.put("enabled", enabled);
        
        try {
            ResponseEntity<String> response = httpClient.postForEntity(
                backendBaseUrl + "/simulation/llm-mode",
                requestBody,
                String.class
            );
            
            if (response.getStatusCode().is2xxSuccessful()) {
                log.info("  LLM mode configured via backend: enabled={}", enabled);
                log.info("  Response: {}", response.getBody());
            } else {
                log.warn("  Failed to configure LLM mode via backend: {}", response.getStatusCode());
                log.warn("  Response: {}", response.getBody());
            }
        } catch (Exception e) {
            log.warn("  Failed to configure LLM mode via backend: {}", e.getMessage());
            // Don't fail the test - LLM mode might be configured via environment variables
        }
        
        // Also configure directly via support service
        try {
            Map<String, Object> supportConfig = new HashMap<>();
            supportConfig.put("recommendation_mode", enabled ? "llm" : "heuristic");
            supportConfig.put("agent_decision_mode", enabled ? "llm" : "heuristic");
            supportConfig.put("enable_llm_coordination", enabled);
            supportConfig.put("enable_agent_communication", enabled);
            
            ResponseEntity<Map> response = httpClient.postForEntity(
                supportBaseUrl + "/config",
                supportConfig,
                Map.class
            );
            
            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                log.info("  LLM mode configured via support service: enabled={}", enabled);
                Map config = (Map) response.getBody().get("config");
                log.info("  Config: {}", config);
            } else {
                log.warn("  Failed to configure LLM mode via support service: {}", response.getStatusCode());
            }
        } catch (Exception e) {
            log.warn("  Failed to configure LLM mode via support service: {}", e.getMessage());
        }
    }
    
    /**
     * Check if a service is running by calling its health endpoint.
     */
    private boolean isServiceRunning(String baseUrl) {
        try {
            String healthUrl = baseUrl + "/health";
            log.debug("Checking service health: {}", healthUrl);
            ResponseEntity<String> response = httpClient.getForEntity(
                healthUrl,
                String.class
            );
            boolean isHealthy = response.getStatusCode().is2xxSuccessful();
            if (isHealthy) {
                log.debug("  Service is healthy: {}", response.getBody());
            } else {
                log.warn("  Service returned non-2xx status: {}", response.getStatusCode());
            }
            return isHealthy;
        } catch (Exception e) {
            log.warn("Service at {} is not reachable: {}", baseUrl, e.getMessage());
            if (log.isDebugEnabled()) {
                e.printStackTrace();
            }
            return false;
        }
    }
}
