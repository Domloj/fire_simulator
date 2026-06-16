package pl.edu.agh.kis.firebackend.service;

import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Delivery;

import lombok.AllArgsConstructor;
import pl.edu.agh.kis.firebackend.configuration.RoutingKeys;
import pl.edu.agh.kis.firebackend.service.model.UpdatesQueue;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.rabbitmq.BindingSpecification;
import reactor.rabbitmq.ExchangeSpecification;
import reactor.rabbitmq.OutboundMessage;
import reactor.rabbitmq.QueueSpecification;
import reactor.rabbitmq.Receiver;
import reactor.rabbitmq.Sender;

@Service
@AllArgsConstructor
public class StateUpdatesService 
{
    private Sender sender;
    private Receiver receiver;
    private ObjectMapper mapper;
    private String exchangeName;

    private static final Logger log = LoggerFactory.getLogger(StateUpdatesService.class);

    public <T> Flux<T> createUpdatesFlux(UpdatesQueue<T> queue)
    {
        log.debug("Creating Flux for queue: {} (class: {})", queue.name(), queue.eventClass().getSimpleName());
        
        String routingKey = RoutingKeys.getRoutingKey(queue.name());
        log.debug("Queue {} mapped to routing key: {}", queue.name(), routingKey);
        
        // Declare exchange first (topic type)
        // Declare queue with durable=false to match simulator's queue creation
        // Bind queue to exchange with routing key
        return sender.declareExchange(ExchangeSpecification.exchange(exchangeName).type("topic").durable(false))
            .doOnSuccess(ok -> log.debug("Exchange declared/verified: {}", exchangeName))
            .then(sender.declare(QueueSpecification.queue(queue.name()).durable(false)))
            .doOnSuccess(ok -> log.debug("Queue declared/verified: {}", queue.name()))
            .doOnError(e -> log.error("Failed to declare queue {}: {}", queue.name(), e.toString()))
            .then(sender.bind(BindingSpecification.binding()
                .exchange(exchangeName)
                .queue(queue.name())
                .routingKey(routingKey)))
            .doOnSuccess(ok -> log.info("Queue {} bound to exchange {} with routing key {}", queue.name(), exchangeName, routingKey))
            .doOnError(e -> log.error("Failed to bind queue {} to exchange {} with routing key {}: {}", 
                queue.name(), exchangeName, routingKey, e.toString()))
            .thenMany(receiver.consumeAutoAck(queue.name()))
            .doOnSubscribe(sub -> {
                log.debug("Subscribed to queue: {}", queue.name());
            })
            .mapNotNull(message -> 
            {
                try
                {
                    return parseMessage(message, queue.eventClass());
                }
                catch (IOException e)
                {
                    log.error("Failed to parse RMQ message from queue {}: {}", queue.name(), e.toString());
                    return null;
                }
            })
            .onErrorResume(e -> 
            {
                log.error("Error during message consumption from queue {}: {}", queue.name(), e.toString());
                return Flux.empty();
            });
    }


    private <T> T parseMessage(Delivery delivery, Class<T> Tclass) throws IOException 
    {
        return mapper.readValue(delivery.getBody(), Tclass);        
    }

    public <T> Mono<Void> sendMessageToQueue(String queueName, T message) 
    {
        String routingKey = RoutingKeys.getRoutingKey(queueName);
        log.debug("Sending message to queue: {} with routing key: {}", queueName, routingKey);

        try 
        {
            byte[] messageBytes = mapper.writeValueAsBytes(message);
            // Use exchange and routing key instead of direct queue
            OutboundMessage outboundMessage = new OutboundMessage(exchangeName, routingKey, messageBytes);

            // Declare exchange first (topic type)
            // Declare queue before sending to ensure it exists (durable=false to match simulator)
            // Bind queue to exchange with routing key
            return sender.declareExchange(ExchangeSpecification.exchange(exchangeName).type("topic").durable(false))
                .doOnSuccess(ok -> log.debug("Exchange declared/verified for send: {}", exchangeName))
                .then(sender.declare(QueueSpecification.queue(queueName).durable(false)))
                .doOnSuccess(ok -> log.debug("Queue declared/verified for send: {}", queueName))
                .then(sender.bind(BindingSpecification.binding()
                    .exchange(exchangeName)
                    .queue(queueName)
                    .routingKey(routingKey)))
                .doOnSuccess(ok -> log.debug("Queue {} bound to exchange {} with routing key {} for send", 
                    queueName, exchangeName, routingKey))
                .then(sender.send(Mono.just(outboundMessage)))
                .doOnSubscribe(subscription -> 
                {
                    log.debug("Sending message to exchange {} with routing key {}", exchangeName, routingKey);
                })
                .doOnError(e -> 
                {
                    log.error("Error sending message to exchange {} with routing key {}: {}", 
                        exchangeName, routingKey, e.toString());
                })
                .doFinally(signalType -> 
                {
                    log.debug("Message send finalized with signal: {}", signalType);
                });
        } 
        catch (IOException e) 
        {
            log.error("Failed to serialize message: {}", e.toString());
            return Mono.error(e);
        }
    }


}
