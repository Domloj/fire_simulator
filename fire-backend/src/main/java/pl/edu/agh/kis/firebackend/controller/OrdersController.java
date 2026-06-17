package pl.edu.agh.kis.firebackend.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import lombok.RequiredArgsConstructor;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrderFire;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrderPatrol;
import pl.edu.agh.kis.firebackend.service.HttpRequestService;
import pl.edu.agh.kis.firebackend.service.OrdersService;

@RestController
@RequiredArgsConstructor
@CrossOrigin(origins = "*")
public class OrdersController 
{
    private final OrdersService ordersService;
    private final HttpRequestService httpRequestService;
    private static final Logger log = LoggerFactory.getLogger(OrdersController.class);

    @Value("${FIRE_SIMULATION_SERVICE:fire-simulation-service}")
    private String simulationHost;

    @Value("${SIMULATOR_PORT:5000}")
    private int simulatorPort;

    // Whether to accept orders coming from automated workflows (frontend auto-apply)
    @Value("${SIMULATION_ALLOW_AUTO_ORDERS:false}")
    private boolean allowAutoOrders;

    @PostMapping("/orderFireBrigade")
    public ResponseEntity<String> sentOrderBrigade(@RequestBody FrontOrderFire order){        
        log.info(String.format("Order received: %s", order.toString()));
        String src = order.getSource() == null ? "unknown" : order.getSource();

        if (order.getLocation() != null) {
            log.info("[Backend] [SECTOR-DEPENDENCIES] Fire brigade order received: fireBrigadeId={}, location=({}, {}), isGoToBase={}, source={}", 
                order.getId(), order.getLocation().longitude(), order.getLocation().latitude(), order.isGoToBase(), src);
        } else {
            log.info("[Backend] [SECTOR-DEPENDENCIES] Fire brigade order received: fireBrigadeId={}, location=null, isGoToBase={}, source={}", 
                order.getId(), order.isGoToBase(), src);
        }
        ordersService.processOrder(order);
        return ResponseEntity.ok("Order received!");        
    }

    @PostMapping("/orderForestPatrol")
    public ResponseEntity<String> sentOrderPatrol(@RequestBody FrontOrderPatrol order){
        log.info(String.format("Order received: %s", order.toString()));        
        String src = order.getSource() == null ? "unknown" : order.getSource();
        log.info("[Backend] Forester patrol order received: foresterPatrolId={}, isGoToBase={}, source={}", order.getId(), order.isGoToBase(), src);
        ordersService.processOrder(order);
        return ResponseEntity.ok("Order received!");
    }



    

}