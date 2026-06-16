package pl.edu.agh.kis.firebackend.service;

import java.time.Duration;
import java.util.Optional;
import java.util.List;
import java.util.ArrayList;
import java.util.Date;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import org.springframework.beans.factory.annotation.Qualifier;
import pl.edu.agh.kis.firebackend.configuration.QueueNames;
import pl.edu.agh.kis.firebackend.service.model.configuration.Configuration;
import pl.edu.agh.kis.firebackend.model.events.EvCO2Sensor;
import pl.edu.agh.kis.firebackend.model.events.EvCamera;
import pl.edu.agh.kis.firebackend.model.events.EvFireBrigade;
import pl.edu.agh.kis.firebackend.model.events.EvForestPatrol;
import pl.edu.agh.kis.firebackend.model.events.EvLitterMoistureSensor;
import pl.edu.agh.kis.firebackend.model.events.EvPM25ConcentrationSensor;
import pl.edu.agh.kis.firebackend.model.events.EvRecommendation;
import pl.edu.agh.kis.firebackend.model.events.EvSectorState;
import pl.edu.agh.kis.firebackend.model.events.EvLlmChat;
import pl.edu.agh.kis.firebackend.model.events.EvFireBrigadeBatch;
import pl.edu.agh.kis.firebackend.model.events.EvForesterPatrolBatch;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontSectorUpdateFast;
import pl.edu.agh.kis.firebackend.model.events.RecommendedAction;
import pl.edu.agh.kis.firebackend.model.events.EvTempAndAirHumiditySensor;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrderFire;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrderPatrol;
import pl.edu.agh.kis.firebackend.model.primitives.Location;
import pl.edu.agh.kis.firebackend.model.events.EvWindDirectionSensor;
import pl.edu.agh.kis.firebackend.model.events.EvWindSpeedSensor;
import pl.edu.agh.kis.firebackend.service.model.simulation.FireBrigade;
import pl.edu.agh.kis.firebackend.service.model.simulation.ForesterPatrol;
import pl.edu.agh.kis.firebackend.service.model.simulation.Sector;
import pl.edu.agh.kis.firebackend.service.model.simulation.SimulationState;
import pl.edu.agh.kis.firebackend.service.model.simulation.SimulationStateDto;
import pl.edu.agh.kis.firebackend.service.model.SectorState;
import pl.edu.agh.kis.firebackend.service.model.FireState;
import pl.edu.agh.kis.firebackend.service.model.ThreatLevel;
import pl.edu.agh.kis.firebackend.util.SectorIdResolver;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;
import reactor.core.scheduler.Schedulers;

@Service
public class SimulationStateService {
    private StateUpdatesService stateUpdatesService;
    private OrdersService ordersService;
    private Flux<EvFireBrigadeBatch> fireBrigadeBatchFlux;
    private Flux<EvForesterPatrolBatch> foresterPatrolBatchFlux;

    // Incoming telemetry/event streams
    private Flux<EvFireBrigade> fireBrigadeFlux;
    private Flux<EvForestPatrol> foresterPatrolFlux;
    private Flux<EvWindSpeedSensor> windSpeedSensorFlux;
    private Flux<EvTempAndAirHumiditySensor> tempAndAirHumiditySensorFlux;
    private Flux<EvWindDirectionSensor> windDirectionSensorFlux;
    private Flux<EvLitterMoistureSensor> litterMoistureSensorFlux;
    private Flux<EvCO2Sensor> co2SensorFlux;
    private Flux<EvPM25ConcentrationSensor> pm25ConcentrationSensorFlux;
    private Flux<EvCamera> cameraFlux;
    private Flux<EvRecommendation> recommendationFlux;
    private Flux<EvSectorState> sectorStateFlux;
    private Flux<EvSectorState> sectorStateFastFlux;
    private Flux<EvLlmChat> supportLLMRequestsFlux;
    private Flux<EvLlmChat> supportLLMResponsesFlux;
    private Flux<EvLlmChat> supportLLMPropositionsFlux;
    private Flux<EvLlmChat> supportLLMPropositionsResponsesFlux;

    private Sinks.Many<EvLlmChat> llmChatSink;
    private Sinks.Many<Object> agentPositionSink;

    private final AtomicLong lastRecommendationNotificationTime = new AtomicLong(0);
    private static final long RECOMMENDATION_NOTIFICATION_THROTTLE_MS = 4000L;

    private final AtomicLong lastFastSectorUpdateTime = new AtomicLong(0);
    private static final long FAST_SECTOR_UPDATE_THROTTLE_MS = 200L;

    private Sinks.Many<FrontSectorUpdateFast> fastSectorUpdatesSink = Sinks.many().multicast().onBackpressureBuffer();

    public SimulationStateService(
            StateUpdatesService stateUpdatesService,
            OrdersService ordersService,
            Flux<EvFireBrigade> fireBrigadeFlux,
            Flux<EvFireBrigadeBatch> fireBrigadeBatchFlux,
            Flux<EvForestPatrol> foresterPatrolFlux,
            Flux<EvForesterPatrolBatch> foresterPatrolBatchFlux,
            Flux<EvWindSpeedSensor> windSpeedSensorFlux,
            Flux<EvTempAndAirHumiditySensor> tempAndAirHumiditySensorFlux,
            Flux<EvWindDirectionSensor> windDirectionSensorFlux,
            Flux<EvLitterMoistureSensor> litterMoistureSensorFlux,
            Flux<EvCO2Sensor> co2SensorFlux,
            Flux<EvPM25ConcentrationSensor> pm25ConcentrationSensorFlux,
            Flux<EvCamera> cameraFlux,
            Flux<EvRecommendation> recommendationFlux,
            @Qualifier("simulationState") Flux<EvSectorState> sectorStateFlux,
            @Qualifier("simulationStateFast") Flux<EvSectorState> sectorStateFastFlux,
            @Qualifier("supportLLMRequests") Flux<EvLlmChat> supportLLMRequestsFlux,
            @Qualifier("supportLLMResponses") Flux<EvLlmChat> supportLLMResponsesFlux,
            @Qualifier("supportLLMPropositions") Flux<EvLlmChat> supportLLMPropositionsFlux,
            @Qualifier("supportLLMPropositionsResponses") Flux<EvLlmChat> supportLLMPropositionsResponsesFlux,
            @Qualifier("llmChatSinkShared") Sinks.Many<EvLlmChat> llmChatSink,
            @Qualifier("agentPositionSink") Sinks.Many<Object> agentPositionSink) {
        this.stateUpdatesService = stateUpdatesService;
        this.ordersService = ordersService;
        this.fireBrigadeFlux = fireBrigadeFlux;
        this.fireBrigadeBatchFlux = fireBrigadeBatchFlux;
        this.foresterPatrolFlux = foresterPatrolFlux;
        this.foresterPatrolBatchFlux = foresterPatrolBatchFlux;
        this.windSpeedSensorFlux = windSpeedSensorFlux;
        this.tempAndAirHumiditySensorFlux = tempAndAirHumiditySensorFlux;
        this.windDirectionSensorFlux = windDirectionSensorFlux;
        this.litterMoistureSensorFlux = litterMoistureSensorFlux;
        this.co2SensorFlux = co2SensorFlux;
        this.pm25ConcentrationSensorFlux = pm25ConcentrationSensorFlux;
        this.cameraFlux = cameraFlux;
        this.recommendationFlux = recommendationFlux;
        this.sectorStateFlux = sectorStateFlux;
        this.sectorStateFastFlux = sectorStateFastFlux;
        this.supportLLMRequestsFlux = supportLLMRequestsFlux;
        this.supportLLMResponsesFlux = supportLLMResponsesFlux;
        this.supportLLMPropositionsFlux = supportLLMPropositionsFlux;
        this.supportLLMPropositionsResponsesFlux = supportLLMPropositionsResponsesFlux;
        this.llmChatSink = llmChatSink;
        this.agentPositionSink = agentPositionSink;
    }

    @PostConstruct
    public void init() {
        log.info(
                "SimulationStateService initialized. Auto-execution of recommendations has been removed; frontend must send orders to execute recommendations.");
    }

    private static final Logger log = LoggerFactory.getLogger(SimulationStateService.class);

    private volatile SimulationState currentState = null;
    private volatile SimulationState lastSentState = null;

    private boolean sectorsHaveContours() {
        if (currentState == null) {
            return false;
        }
        synchronized (currentState) {
            if (currentState.sectors.isEmpty()) {
                return false;
            }
            var sectorsSnapshot = new ArrayList<>(currentState.sectors.values());
            return sectorsSnapshot.stream().anyMatch(s -> !s.contours.isEmpty());
        }
    }

    @PostConstruct
    public void initializeMessageConsumers() {
        try {
            String logFile = System.getenv().getOrDefault("LOG_FILE", "logs/application.logs");
            java.nio.file.Path logPath = java.nio.file.Paths.get(logFile).getParent();
            if (logPath != null) {
                java.nio.file.Files.createDirectories(logPath);
            }
        } catch (Exception e) {
            log.warn("Failed to ensure log directory exists: {}", e.toString());
        }

        currentState = new SimulationState();
        subscribeToQueues();
        log.info("RabbitMQ consumers ready");
    }

    private void subscribeToQueues() {
        // Konsumujemy wyłącznie kolejki batch. Wcześniej dodatkowo subskrybowany
        // był pojedynczy flux agentów i ten sam agent był przetwarzany dwa razy
        // na tick, z dwóch wątków (Schedulers.parallel()). Dwie równoległe
        // kolejki nie mają gwarancji kolejności, więc spóźniona pojedyncza
        // wiadomość nadpisywała nowszą pozycję z batcha -> teleportujący się
        // agenci. Jedna kolejka batch zachowuje kolejność FIFO z RabbitMQ.
        fireBrigadeBatchFlux.subscribeOn(Schedulers.parallel())
                .subscribe(batch -> {
                    if (batch != null && batch.batch() != null) {
                        log.debug("Received fireBrigade batch with {} agents", batch.batch().size());
                        batch.batch().forEach(this::processFireBrigade);
                        // Emit single batch update to frontend for efficiency
                        emitAgentBatchPosition(batch.batch(), "fireBrigade");
                    } else {
                        log.warn("Received null fireBrigade batch or batch.batch() is null");
                    }
                });

        foresterPatrolBatchFlux.subscribeOn(Schedulers.parallel())
                .subscribe(batch -> {
                    if (batch != null && batch.batch() != null) {
                        log.debug("Received foresterPatrol batch with {} agents", batch.batch().size());
                        batch.batch().forEach(this::processForesterPatrol);
                        emitAgentBatchPosition(batch.batch(), "foresterPatrol");
                    } else {
                        log.warn("Received null foresterPatrol batch or batch.batch() is null");
                    }
                });

        windSpeedSensorFlux
                .subscribeOn(Schedulers.parallel())
                .subscribe(windSpeedSensor -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver.resolveSectorId(
                            currentState.sectors.values().stream().toList(), windSpeedSensor.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for wind speed sensor!", windSpeedSensor.location());
                        return;
                    }

                    Integer sectorId = sectorIdOptional.get();
                    var windSpeed = windSpeedSensor.data().windSpeed();

                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when updating wind speed sensor at location {}",
                                    sectorId, windSpeedSensor.location());
                            return;
                        }
                        sector.state.windSpeed = windSpeed;
                    }
                });

        tempAndAirHumiditySensorFlux.subscribeOn(Schedulers.parallel())
                .subscribe(tempAndAirHumiditySensor -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver.resolveSectorId(
                            currentState.sectors.values().stream().toList(), tempAndAirHumiditySensor.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for temperature and humidity sensor!",
                                tempAndAirHumiditySensor.location());
                        return;
                    }
                    Integer sectorId = sectorIdOptional.get();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when updating temperature/humidity sensor at location {}",
                                    sectorId, tempAndAirHumiditySensor.location());
                            return;
                        }
                        sector.state.temperature = tempAndAirHumiditySensor.data().temperature();
                        sector.state.airHumidity = tempAndAirHumiditySensor.data().airHumidity();
                    }
                });

        windDirectionSensorFlux.subscribeOn(Schedulers.parallel())
                .subscribe(windDirectionSensor -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver.resolveSectorId(
                            currentState.sectors.values().stream().toList(), windDirectionSensor.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for wind direction sensor!",
                                windDirectionSensor.location());
                        return;
                    }
                    Integer sectorId = sectorIdOptional.get();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when updating wind direction sensor at location {}",
                                    sectorId, windDirectionSensor.location());
                            return;
                        }
                        sector.state.windDirection = windDirectionSensor.data().toDirection();
                    }
                });

        litterMoistureSensorFlux.subscribeOn(Schedulers.parallel())
                .subscribe(litterMoistureSensor -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver.resolveSectorId(
                            currentState.sectors.values().stream().toList(), litterMoistureSensor.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for litter moisture sensor!",
                                litterMoistureSensor.location());
                        return;
                    }
                    Integer sectorId = sectorIdOptional.get();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when updating litter moisture sensor at location {}",
                                    sectorId, litterMoistureSensor.location());
                            return;
                        }
                        sector.state.plantLitterMoisture = litterMoistureSensor.data().litterMoisture();
                    }
                });

        co2SensorFlux.subscribeOn(Schedulers.parallel())
                .subscribe(co2Sensor -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver
                            .resolveSectorId(currentState.sectors.values().stream().toList(), co2Sensor.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for CO2 sensor!", co2Sensor.location());
                        return;
                    }
                    Integer sectorId = sectorIdOptional.get();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when updating CO2 sensor at location {}",
                                    sectorId, co2Sensor.location());
                            return;
                        }
                        sector.state.co2Concentration = co2Sensor.data().co2Concentration();
                    }
                });

        pm25ConcentrationSensorFlux.subscribeOn(Schedulers.parallel())
                .subscribe(pm25ConcentrationSensor -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver.resolveSectorId(
                            currentState.sectors.values().stream().toList(), pm25ConcentrationSensor.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for PM2.5 concentration sensor!",
                                pm25ConcentrationSensor.location());
                        return;
                    }
                    Integer sectorId = sectorIdOptional.get();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when updating PM2.5 sensor at location {}",
                                    sectorId, pm25ConcentrationSensor.location());
                            return;
                        }
                        sector.state.pm2_5Concentration = pm25ConcentrationSensor.data().pm2_5Concentration();
                    }
                });

        cameraFlux.subscribeOn(Schedulers.parallel())
                .subscribe(camera -> {
                    if (!sectorsHaveContours()) {
                        return;
                    }

                    Optional<Integer> sectorIdOptional = SectorIdResolver
                            .resolveSectorId(currentState.sectors.values().stream().toList(), camera.location());
                    if (sectorIdOptional.isEmpty()) {
                        log.warn("Sector at location {} not found for camera!", camera.location());
                        return;
                    }
                    Integer sectorId = sectorIdOptional.get();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            log.error(
                                    "Resource not found: Sector {} does not exist when processing camera data at location {}",
                                    sectorId, camera.location());
                            return;
                        }
                        // TODO: Handle camera data in some way
                    }
                });

        recommendationFlux.subscribeOn(Schedulers.parallel())
                .subscribe(recommendation -> {
                    log.info("Received recommendation message: {} actions",
                            recommendation.recommendedActions() != null ? recommendation.recommendedActions().size()
                                    : 0);


                    // long now = System.currentTimeMillis();
                    // long lastNotification = lastRecommendationNotificationTime.get();
                    // if (now - lastNotification >= RECOMMENDATION_NOTIFICATION_THROTTLE_MS) {
                    //     if (lastRecommendationNotificationTime.compareAndSet(lastNotification, now)) {
                    //         llmChatSink.tryEmitNext(new EvLlmChat(
                    //                 null, // agentId
                    //                 "system_event", // type
                    //                 null, // action
                    //                 null, // sectorId
                    //                 null, // priority
                    //                 "Recommendation engine (MCTS) published " +
                    //                         (recommendation.recommendedActions() != null
                    //                                 ? recommendation.recommendedActions().size()
                    //                                 : 0)
                    //                         +
                    //                         " new tactical actions", // description
                    //                 null, // location
                    //                 java.time.Instant.now().toString(), // timestamp
                    //                 "info", // status
                    //                 null, // content
                    //                 "System" // source
                    //         ));
                    //     }
                    // }

                    // List<RecommendedAction> actions = recommendation.recommendedActions();
                    // if (actions == null) {
                    //     log.warn("Received recommendation with null recommendedActions list at timestamp: {}",
                    //             recommendation.timestamp());
                    //     return;
                    // }

                    // for (RecommendedAction action : actions) {
                    //     String unitType = action.unitType();
                    //     if (unitType == null || unitType.isEmpty()) {
                    //         log.error(
                    //                 "Received recommendation without unitType for unitId={}, sectorId={}. Skipping to avoid misrouting.",
                    //                 action.unitId(), action.sectorId());
                    //         continue;
                    //     }
                    //     boolean exists;
                    //     synchronized (currentState) {
                    //         if ("fireBrigade".equals(unitType)) {
                    //             exists = currentState.fireBrigades.containsKey(action.unitId());
                    //         } else if ("foresterPatrol".equals(unitType)) {
                    //             exists = currentState.foresterPatrols.containsKey(action.unitId());
                    //         } else {
                    //             exists = false;
                    //         }
                    //     }
                    //     if (!exists) {
                    //         log.warn("Dropping recommendation for unknown unitType={} unitId={} (sectorId={})",
                    //                 unitType, action.unitId(), action.sectorId());
                    //         continue;
                    //     }

                    //     // Create composite key to avoid ID conflicts
                    //     String compositeKey = unitType + ":" + action.unitId();

                    //     synchronized (currentState) {
                    //         currentState.recommendedActions.put(compositeKey, action);
                    //     }

                    //     // AUTOMATIC EXECUTION: Convert recommendation to order and send to simulation
                    //     try {
                    //         Integer sectorId = action.sectorId();
                    //         if (sectorId != null && sectorId > 0) {
                    //             Sector targetSector;
                    //             synchronized (currentState) {
                    //                 targetSector = currentState.sectors.get(sectorId);
                    //             }

                    //             if (targetSector != null && targetSector.contours != null
                    //                     && !targetSector.contours.isEmpty()) {
                    //                 // Calculate center of sector for location
                    //                 double centerLat = 0.0;
                    //                 double centerLon = 0.0;
                    //                 for (List<Double> contour : targetSector.contours) {
                    //                     if (contour.size() >= 2) {
                    //                         centerLat += contour.get(1);
                    //                         centerLon += contour.get(0);
                    //                     }
                    //                 }
                    //                 if (targetSector.contours.size() > 0) {
                    //                     centerLat /= targetSector.contours.size();
                    //                     centerLon /= targetSector.contours.size();
                    //                 }

                    //                 Location location = new Location((float) centerLon, (float) centerLat);

                    //                 // Auto-execution disabled by design: backend will NOT send orders for
                    //                 // recommendations.
                    //                 // The UI/Frontend must explicitly send an order to the backend to execute a
                    //                 // recommendation.
                    //                 log.info(
                    //                         "Backend skips auto-execution of recommendation for {} {} -> Sector {}. Frontend must send order to execute.",
                    //                         unitType, action.unitId(), sectorId);
                    //             } else {
                    //                 log.warn("Cannot auto-execute recommendation: Sector {} not found or invalid",
                    //                         sectorId);
                    //             }
                    //         }
                    //     } catch (Exception e) {
                    //         log.error("Failed to auto-execute recommendation for {} {} -> Sector {}: {}",
                    //                 unitType, action.unitId(), action.sectorId(), e.getMessage());
                    //     }
                    // }

                    // --- ACTIVE: expose recommendations to frontend via SSE (without auto-apply) ---
                    var actions = recommendation.recommendedActions();
                    if (actions == null) {
                        log.warn("Received recommendation with null recommendedActions list at timestamp: {}",
                                recommendation.timestamp());
                        return;
                    }

                    synchronized (currentState) {
                        // Clear previous recommendations – frontend always sees the latest set
                        currentState.recommendedActions.clear();

                        for (var action : actions) {
                            if (action == null) {
                                continue;
                            }
                            String unitType = action.unitType();
                            Integer unitId = action.unitId();
                            Integer sectorId = action.sectorId();

                            if (unitType == null || unitType.isEmpty() || unitId == null || sectorId == null) {
                                log.warn("Skipping invalid recommendation: unitType={}, unitId={}, sectorId={}",
                                        unitType, unitId, sectorId);
                                continue;
                            }

                            boolean exists;
                            if ("fireBrigade".equals(unitType)) {
                                exists = currentState.fireBrigades.containsKey(unitId);
                            } else if ("foresterPatrol".equals(unitType)) {
                                exists = currentState.foresterPatrols.containsKey(unitId);
                            } else {
                                exists = false;
                            }

                            if (!exists) {
                                log.debug("Dropping recommendation for unknown unitType={} unitId={} (sectorId={})",
                                        unitType, unitId, sectorId);
                                continue;
                            }

                            String compositeKey = unitType + ":" + unitId;
                            currentState.recommendedActions.put(compositeKey, action);
                        }
                    }
                });

        sectorStateFlux.subscribeOn(Schedulers.parallel())
                .subscribe(sectorState -> {
                    log.debug(
                            "Received sector state update: sectorId={}, fireLevel={}, burnLevel={}, extinguishLevel={}",
                            sectorState.sectorId(), sectorState.fireLevel(), sectorState.burnLevel(),
                            sectorState.extinguishLevel());
                    Integer sectorId = sectorState.sectorId();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            SectorState state = new SectorState(
                                    new java.util.Date(),
                                    0.0, 0.0, null, 0.0, 0.0, 0.0, 0.0,
                                    parseThreatLevel(sectorState.threatLevel()),
                                    parseFireState(sectorState.fireState()),
                                    sectorState.fireLevel(),
                                    sectorState.burnLevel(),
                                    sectorState.extinguishLevel());
                            // Create sector with empty contours and no assigned brigades
                            sector = new Sector(sectorId, state, new ArrayList<List<Double>>(),
                                    new ArrayList<Integer>());
                            currentState.sectors.put(sectorId, sector);
                        } else {
                            // Update existing sector
                            sector.state.fireLevel = sectorState.fireLevel();
                            sector.state.burnLevel = sectorState.burnLevel();
                            sector.state.extinguishLevel = sectorState.extinguishLevel();
                            sector.state.fireState = parseFireState(sectorState.fireState());
                            sector.state.threatLevel = parseThreatLevel(sectorState.threatLevel());
                        }
                    }
                });

        sectorStateFastFlux.subscribeOn(Schedulers.parallel())
                .subscribe(sectorState -> {
                    Integer sectorId = sectorState.sectorId();
                    synchronized (currentState) {
                        var sector = currentState.sectors.get(sectorId);
                        if (sector == null) {
                            SectorState state = new SectorState(
                                    new java.util.Date(),
                                    0.0, 0.0, null, 0.0, 0.0, 0.0, 0.0,
                                    parseThreatLevel(sectorState.threatLevel()),
                                    parseFireState(sectorState.fireState()),
                                    sectorState.fireLevel(),
                                    sectorState.burnLevel(),
                                    sectorState.extinguishLevel());
                            sector = new Sector(sectorId, state, new ArrayList<List<Double>>(),
                                    new ArrayList<Integer>());
                            currentState.sectors.put(sectorId, sector);
                        } else {
                            sector.state.fireLevel = sectorState.fireLevel();
                            sector.state.burnLevel = sectorState.burnLevel();
                            sector.state.extinguishLevel = sectorState.extinguishLevel();
                            sector.state.fireState = parseFireState(sectorState.fireState());
                            sector.state.threatLevel = parseThreatLevel(sectorState.threatLevel());
                        }
                    }

                    // OPTIMIZATION: Throttle fast sector updates to reduce frontend load
                    // Only send updates at most once per 200ms (5fps) to match main state updates
                    long now = System.currentTimeMillis();
                    long lastUpdate = lastFastSectorUpdateTime.get();
                    if (now - lastUpdate >= FAST_SECTOR_UPDATE_THROTTLE_MS) {
                        if (lastFastSectorUpdateTime.compareAndSet(lastUpdate, now)) {
                            fastSectorUpdatesSink.tryEmitNext(
                                    new FrontSectorUpdateFast("sector_update_fast", List.of(sectorState)));
                        }
                    }
                    // If throttled, the state is still updated in currentState above,
                    // it will be sent in the next main state update
                });

        supportLLMRequestsFlux.subscribeOn(Schedulers.parallel())
                .subscribe(request -> {
                    log.debug("Received support LLM request from agent: {}", request.agentId());
                    llmChatSink.tryEmitNext(request);
                });

        supportLLMResponsesFlux.subscribeOn(Schedulers.parallel())
                .subscribe(response -> {
                    log.debug("Received support LLM response: {}", response.type());
                    llmChatSink.tryEmitNext(response);
                });

        supportLLMPropositionsFlux.subscribeOn(Schedulers.parallel())
                .subscribe(proposition -> {
                    log.debug("Received support LLM proposition from agent: {}", proposition.agentId());
                    llmChatSink.tryEmitNext(proposition);
                });

        supportLLMPropositionsResponsesFlux.subscribeOn(Schedulers.parallel())
                .subscribe(response -> {
                    log.debug("Received support LLM proposition response: {}", response.type());
                    llmChatSink.tryEmitNext(response);
                });
    }

    private void processFireBrigade(EvFireBrigade fireBrigade) {
        Integer key = fireBrigade.fireBrigadeId();
        Location location = fireBrigade.location();
        
        // FIX: Use fallback location from currentState if location is null
        if (location == null) {
            synchronized (currentState) {
                FireBrigade existing = currentState.fireBrigades.get(key);
                if (existing != null && existing.location() != null) {
                    location = existing.location();
                    log.debug("processFireBrigade: fireBrigade {} using fallback location from currentState", key);
                } else {
                    log.warn("processFireBrigade: fireBrigade {} has null location and no fallback available - skipping update", key);
                    return; // Skip update if no location available
                }
            }
        }
        
        synchronized (currentState) {
            Integer sectorId = fireBrigade.sectorId();
            if (sectorId == null || sectorId == 0) {
                if (sectorsHaveContours() && location != null) {
                    var resolvedSectorId = SectorIdResolver.resolveSectorId(
                            currentState.sectors.values().stream().toList(),
                            location);
                    if (resolvedSectorId.isPresent()) {
                        sectorId = resolvedSectorId.get();
                    } else {
                        sectorId = 0;
                    }
                } else {
                    sectorId = 0;
                }
            }
            var brigade = new FireBrigade(
                    fireBrigade.fireBrigadeId(),
                    sectorId,
                    location, // Use fallback location if original was null
                    fireBrigade.state(),
                    pl.edu.agh.kis.firebackend.service.model.FireBrigadeAction.EXTINGUISH);
            currentState.fireBrigades.put(key, brigade);
        }

        // Also emit single agent update for non-batch path (legacy support)
        // emitAgentPosition(fireBrigade, "fireBrigade");
    }

    private void processForesterPatrol(EvForestPatrol foresterPatrol) {
        Integer key = foresterPatrol.foresterPatrolId();
        synchronized (currentState) {
            currentState.foresterPatrols.put(key, ForesterPatrol.from(foresterPatrol));
        }
    }

    private <T> void emitAgentBatchPosition(List<T> agents, String unitType) {
        try {
            List<java.util.Map<String, Object>> positions = new ArrayList<>();
            int skippedCount = 0;
            for (T agent : agents) {
                if (agent instanceof EvFireBrigade fb) {
                    Location loc = fb.location();
                    // Fallback: try to get location from currentState if null
                    if (loc == null) {
                        synchronized (currentState) {
                            FireBrigade existing = currentState.fireBrigades.get(fb.fireBrigadeId());
                            if (existing != null && existing.location() != null) {
                                loc = existing.location();
                                log.debug("Using fallback location for fireBrigade {} from currentState", fb.fireBrigadeId());
                            }
                        }
                    }
                    if (loc == null) {
                        skippedCount++;
                        log.warn("Skipping fireBrigade {} - location is null and no fallback available", fb.fireBrigadeId());
                        continue;
                    }
                    positions.add(java.util.Map.of(
                            "id", fb.fireBrigadeId(),
                            "longitude", loc.longitude(),
                            "latitude", loc.latitude(),
                            "timestamp", java.time.Instant.now().toString(),
                            "unitType", "fireBrigade",
                            "state", fb.state() != null ? fb.state().toString() : "AVAILABLE"));
                } else if (agent instanceof EvForestPatrol fp) {
                    Location loc = fp.location();
                    // Fallback: try to get location from currentState if null
                    if (loc == null) {
                        synchronized (currentState) {
                            ForesterPatrol existing = currentState.foresterPatrols.get(fp.foresterPatrolId());
                            if (existing != null && existing.location() != null) {
                                loc = existing.location();
                                log.debug("Using fallback location for foresterPatrol {} from currentState", fp.foresterPatrolId());
                            }
                        }
                    }
                    if (loc == null) {
                        skippedCount++;
                        log.warn("Skipping foresterPatrol {} - location is null and no fallback available", fp.foresterPatrolId());
                        continue;
                    }
                    positions.add(java.util.Map.of(
                            "id", fp.foresterPatrolId(),
                            "longitude", loc.longitude(),
                            "latitude", loc.latitude(),
                            "timestamp", java.time.Instant.now().toString(),
                            "unitType", "foresterPatrol",
                            "state", fp.state() != null ? fp.state().toString() : "AVAILABLE"));
                }
            }
            if (skippedCount > 0) {
                log.warn("Skipped {} agents with missing locations in batch (total: {}, valid: {})", skippedCount, agents.size(), positions.size());
            }
            if (positions.isEmpty()) {
                // Don't emit empty position batches
                return;
            }
            java.util.Map<String, Object> payload = java.util.Map.of(
                    "type", "agent_positions", // plural type for parsing optimization
                    "data", positions);
            agentPositionSink.tryEmitNext(payload);
        } catch (Exception e) {
            log.error("Failed to emit batch agent_position message: {}", e.toString(), e);
        }
    }

    public Flux<Object> runSimulation(Configuration configuration, Duration interval) {
        log.info("Starting simulation - interval: {}s, sectors: {}, brigades: {}, patrols: {}",
                interval.getSeconds(), configuration.sectors().size(),
                configuration.fireBrigades().size(), configuration.foresterPatrols().size());

        // Notify UI about simulation start
        llmChatSink.tryEmitNext(new EvLlmChat(
                null, // agentId
                "system_event", // type
                null, // action
                null, // sectorId
                null, // priority
                "Simulation session started: " + configuration.forestName() +
                        " (" + configuration.sectors().size() + " sectors, " +
                        configuration.fireBrigades().size() + " brigades)", // description
                null, // location
                java.time.Instant.now().toString(), // timestamp
                "info", // status
                null, // content
                "System" // source
        ));

        synchronized (currentState) {
            // Każde nowe uruchomienie symulacji traktujemy jako NOWĄ sesję –
            // resetujemy cały stan w backendzie, żeby nie mieszać sektorów z poprzedniego runu.
            var configState = SimulationState.from(configuration);

            currentState.forestName = configState.forestName;
            currentState.timestamp = null;
            currentState.tick = 0L;

            currentState.sectors.clear();
            currentState.sectors.putAll(configState.sectors);

            currentState.fireBrigades.clear();
            currentState.fireBrigades.putAll(configState.fireBrigades);

            currentState.foresterPatrols.clear();
            currentState.foresterPatrols.putAll(configState.foresterPatrols);

            // Wyczyszczenie rekomendacji – nowa sesja, nowe decyzje
            currentState.recommendedActions.clear();

            // Po pełnym resecie lastSentState nie ma sensu – będzie odbudowany przy potrzebie optymalnych update’ów
            lastSentState = null;

            log.info("State reset for new simulation - sectors: {}, brigades: {}, patrols: {}",
                    currentState.sectors.size(), currentState.fireBrigades.size(), currentState.foresterPatrols.size());

            // Note: Configuration should be published by fire-simulation service, not by
            // backend
            // Backend only consumes from RabbitMQ and sends to frontend via SSE
        }

        Flux<SimulationStateDto> stateFlux = Flux.interval(interval)
                .onBackpressureLatest() // Handle backpressure - keep only latest state when consumer is slow
                .map(tick -> {
                    synchronized (currentState) {
                        currentState.timestamp = new Date();
                        currentState.tick = tick;
                        SimulationStateDto dto = SimulationStateDto.from(currentState);

                        // Send full state via SSE (frontend needs complete state)

                        // Note: Support service should receive data from fire-simulation directly via
                        // RabbitMQ
                        // Backend only aggregates data for frontend via SSE, not for support service

                        return dto;
                    }
                });

        // Merge all flux streams and handle client disconnections gracefully
        // Broken pipe errors are normal when client closes SSE connection - don't log
        // as errors
        return Flux
                .merge(stateFlux, fastSectorUpdatesSink.asFlux(), llmChatSink.asFlux().cast(Object.class),
                        agentPositionSink.asFlux().cast(Object.class))
                .doOnError(error -> {
                    // Only log non-IO errors (Broken pipe is normal for SSE disconnections)
                    if (!(error instanceof java.io.IOException) &&
                            !(error.getCause() instanceof java.io.IOException) &&
                            !error.getMessage().contains("Broken pipe")) {
                        log.error("Error in simulation SSE stream", error);
                    } else {
                        // Client disconnected - this is normal, log at debug level
                        log.debug("Client disconnected from SSE stream: {}", error.getMessage());
                    }
                })
                .onErrorResume(error -> {
                    // For IO errors (broken pipe), just complete the stream silently
                    if (error instanceof java.io.IOException ||
                            (error.getCause() instanceof java.io.IOException) ||
                            error.getMessage().contains("Broken pipe")) {
                        return Flux.empty();
                    }
                    // For other errors, propagate them
                    return Flux.error(error);
                });
    }

    public void assignBrigadesToSector(final int sectorId, final List<Integer> brigades) {
        synchronized (currentState) {
            var sector = currentState.sectors.get(sectorId);
            if (sector == null) {
                log.error("Resource not found: Sector {} does not exist when attempting to assign brigades {}",
                        sectorId, brigades);
                return;
            }
            sector.assignedBrigades = brigades == null ? new ArrayList<>() : new ArrayList<>(brigades);
        }
    }

    /**
     * NOTE: This method is deprecated. Support service receives data directly from
     * fire-simulation via RabbitMQ.
     * Backend only aggregates data for frontend via SSE.
     * Keeping method for now but it's not called anymore.
     */
    @Deprecated
    private void sendOptimizedUpdateToQueue(long tick) {
        if (lastSentState == null) {
            // First update - send full state
            SimulationStateDto fullDto = SimulationStateDto.from(currentState);
            stateUpdatesService.sendMessageToQueue(QueueNames.SUPPORT_AGGREGATED_DATA, fullDto)
                    .doOnError(e -> log.error("Failed to publish initial state to support service: {}", e.toString()))
                    .subscribe();
            lastSentState = cloneState(currentState);
            return;
        }

        // Calculate and send only changed entities
        List<Sector> changedSectors = new ArrayList<>();
        List<FireBrigade> changedBrigades = new ArrayList<>();
        List<ForesterPatrol> changedPatrols = new ArrayList<>();
        List<pl.edu.agh.kis.firebackend.model.events.RecommendedAction> newRecommendations = new ArrayList<>();

        // Find changed sectors (only fire/burn/extinguish levels or assigned brigades
        // changed)
        for (var entry : currentState.sectors.entrySet()) {
            var currentSector = entry.getValue();
            var lastSector = lastSentState.sectors.get(entry.getKey());

            if (lastSector == null ||
                    currentSector.state.fireLevel != lastSector.state.fireLevel ||
                    currentSector.state.burnLevel != lastSector.state.burnLevel ||
                    currentSector.state.extinguishLevel != lastSector.state.extinguishLevel ||
                    !currentSector.assignedBrigades.equals(lastSector.assignedBrigades)) {
                changedSectors.add(currentSector);
            }
        }

        // Find changed brigades
        for (var entry : currentState.fireBrigades.entrySet()) {
            var currentBrigade = entry.getValue();
            var lastBrigade = lastSentState.fireBrigades.get(entry.getKey());

            if (lastBrigade == null ||
                    !currentBrigade.location().equals(lastBrigade.location()) ||
                    currentBrigade.state() != lastBrigade.state() ||
                    currentBrigade.sectorId() != lastBrigade.sectorId()) {
                changedBrigades.add(currentBrigade);
            }
        }

        // Find changed patrols
        for (var entry : currentState.foresterPatrols.entrySet()) {
            var currentPatrol = entry.getValue();
            var lastPatrol = lastSentState.foresterPatrols.get(entry.getKey());

            if (lastPatrol == null ||
                    !currentPatrol.location().equals(lastPatrol.location()) ||
                    currentPatrol.state() != lastPatrol.state() ||
                    currentPatrol.sectorId() != lastPatrol.sectorId()) {
                changedPatrols.add(currentPatrol);
            }
        }

        // Find new recommendations
        for (var entry : currentState.recommendedActions.entrySet()) {
            if (!lastSentState.recommendedActions.containsKey(entry.getKey())) {
                newRecommendations.add(entry.getValue());
            }
        }

        // Only send if there are changes
        if (!changedSectors.isEmpty() || !changedBrigades.isEmpty() ||
                !changedPatrols.isEmpty() || !newRecommendations.isEmpty()) {

            // Create optimized DTO with only changed entities
            SimulationStateDto optimizedDto = new SimulationStateDto(
                    currentState.forestName,
                    currentState.timestamp,
                    currentState.tick,
                    changedSectors,
                    changedBrigades,
                    changedPatrols,
                    newRecommendations);

            stateUpdatesService.sendMessageToQueue(QueueNames.SUPPORT_AGGREGATED_DATA, optimizedDto)
                    .doOnError(e -> log.error("Failed to publish optimized state update to support service: {}",
                            e.toString()))
                    .subscribe();

            // Update last sent state
            lastSentState = cloneState(currentState);
        }
    }

    /**
     * Create a deep copy of SimulationState for tracking changes.
     */
    private SimulationState cloneState(SimulationState state) {
        SimulationState cloned = new SimulationState();
        cloned.forestName = state.forestName;
        cloned.timestamp = state.timestamp != null ? new Date(state.timestamp.getTime()) : null;
        cloned.tick = state.tick;

        // Deep copy sectors
        cloned.sectors = new java.util.HashMap<>();
        for (var entry : state.sectors.entrySet()) {
            var sector = entry.getValue();
            var clonedSector = new Sector(
                    sector.sectorId,
                    cloneSectorState(sector.state),
                    new ArrayList<>(sector.contours),
                    new ArrayList<>(sector.assignedBrigades));
            cloned.sectors.put(entry.getKey(), clonedSector);
        }

        // Deep copy brigades
        cloned.fireBrigades = new java.util.HashMap<>();
        for (var entry : state.fireBrigades.entrySet()) {
            cloned.fireBrigades.put(entry.getKey(), entry.getValue());
        }

        // Deep copy patrols
        cloned.foresterPatrols = new java.util.HashMap<>();
        for (var entry : state.foresterPatrols.entrySet()) {
            cloned.foresterPatrols.put(entry.getKey(), entry.getValue());
        }

        // Deep copy recommendations
        cloned.recommendedActions = new java.util.HashMap<>();
        for (var entry : state.recommendedActions.entrySet()) {
            cloned.recommendedActions.put(entry.getKey(), entry.getValue());
        }

        return cloned;
    }

    // Telemetria niesie fireState/threatLevel jako string. Nieznana albo pusta
    // wartość daje null zamiast wyjątku, dzięki czemu reszta aktualizacji sektora
    // przechodzi normalnie.
    private static FireState parseFireState(String value) {
        if (value == null) return null;
        try {
            return FireState.valueOf(value);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private static ThreatLevel parseThreatLevel(String value) {
        if (value == null) return null;
        try {
            return ThreatLevel.valueOf(value);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    private SectorState cloneSectorState(SectorState state) {
        // Create new SectorState with all visible fields
        SectorState cloned = new SectorState(
                state.timestamp != null ? new Date(state.timestamp.getTime()) : null,
                state.temperature,
                state.windSpeed,
                state.windDirection,
                state.airHumidity,
                state.plantLitterMoisture,
                state.co2Concentration,
                state.pm2_5Concentration,
                state.threatLevel,
                state.fireState,
                state.fireLevel,
                state.burnLevel,
                state.extinguishLevel);
        return cloned;
    }
}
