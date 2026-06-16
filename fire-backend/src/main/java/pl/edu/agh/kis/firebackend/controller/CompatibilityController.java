package pl.edu.agh.kis.firebackend.controller;

import lombok.RequiredArgsConstructor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import pl.edu.agh.kis.firebackend.service.model.configuration.Configuration;
import pl.edu.agh.kis.firebackend.service.HttpRequestService;

@RestController
@RequiredArgsConstructor
@CrossOrigin(origins = "*")
public class CompatibilityController 
{
    private static final Logger log = LoggerFactory.getLogger(CompatibilityController.class);
    private final HttpRequestService httpRequestService;

    @Value("${FIRE_SIMULATION_SERVICE:fire-simulation-service}")
    private String simulationHost;

    @Value("${SIMULATOR_PORT:5000}")
    private int simulatorPort;

    @PostMapping("/send-simulation-request")
    public ResponseEntity<String> sendSimulationRequestRoot(@RequestBody Configuration configuration) 
    {
        log.info("Forwarding /send-simulation-request to simulation service at {}:{}", simulationHost, simulatorPort);
        String url = String.format("http://%s:%d/run_simulation", simulationHost, simulatorPort);
        httpRequestService.sendPostRequest(url, configuration);
        return ResponseEntity.ok("Configuration sent to simulation!");
    }
}
