package pl.edu.agh.kis.firebackend.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SimpleTestController 
{
    private static final Logger log = LoggerFactory.getLogger(SimpleTestController.class);

    @GetMapping("/ping")
    public ResponseEntity<String> ping() 
    {
        return ResponseEntity.ok("pong");
    }

    @PostMapping("/send-simulation-request-debug")
    public ResponseEntity<String> debugSend(@RequestBody(required = false) String body) 
    {
        log.info("DEBUG /send-simulation-request-debug body: {}", body);
        return ResponseEntity.ok("ok");
    }
}
