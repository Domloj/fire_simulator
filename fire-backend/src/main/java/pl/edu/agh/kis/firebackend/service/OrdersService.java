package pl.edu.agh.kis.firebackend.service;

import java.util.Date;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import lombok.AllArgsConstructor;
import pl.edu.agh.kis.firebackend.service.model.FireBrigadeAction;
import pl.edu.agh.kis.firebackend.service.model.ForesterPatrolAction;
import pl.edu.agh.kis.firebackend.service.model.OrderFireBrigade;
import pl.edu.agh.kis.firebackend.service.model.OrderForesterPatrol;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrder;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrderFire;
import pl.edu.agh.kis.firebackend.service.model.frontend.FrontOrderPatrol;
import pl.edu.agh.kis.firebackend.configuration.QueueNames;

@Service
@AllArgsConstructor
public class OrdersService {

    private StateUpdatesService stateUpdatesService;
    private static final Logger log = LoggerFactory.getLogger(OrdersService.class);

    public void processOrder(FrontOrder order){
        if(order instanceof FrontOrderFire){
            OrderFireBrigade orderFireBrigade;
            if(order.isGoToBase()){
                orderFireBrigade = new OrderFireBrigade(order.getId(), FireBrigadeAction.GO_TO_BASE, null, new Date(), order.getLocation());
            } else {
                orderFireBrigade = new OrderFireBrigade(order.getId(), FireBrigadeAction.EXTINGUISH, null, new Date(), order.getLocation());
            }
            stateUpdatesService.sendMessageToQueue(QueueNames.SIMULATION_CONTROL_FIRE_BRIGADE_ACTIONS, orderFireBrigade)
                .subscribe(
                    result -> {},
                    error -> log.error("Failed to send fire brigade order to queue: {}", error.getMessage(), error)
                );

        } else if(order instanceof FrontOrderPatrol){
            OrderForesterPatrol orderForestPatrol;
            if(order.isGoToBase()){
                orderForestPatrol = new OrderForesterPatrol(order.getId(), ForesterPatrolAction.GO_TO_BASE, new Date(), order.getLocation());
            } else {
                orderForestPatrol = new OrderForesterPatrol(order.getId(), ForesterPatrolAction.PATROL, new Date(), order.getLocation()); 
            }
            stateUpdatesService.sendMessageToQueue(QueueNames.SIMULATION_CONTROL_FORESTER_ACTIONS, orderForestPatrol)
                .subscribe(
                    result -> {},
                    error -> log.error("Failed to send forester patrol order to queue: {}", error.getMessage(), error)
                );
        } else {
            log.warn("Unknown order type: {}", order.getClass().getName());
        }
    }
}
