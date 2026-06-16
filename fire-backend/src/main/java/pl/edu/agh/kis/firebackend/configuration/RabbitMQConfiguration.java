package pl.edu.agh.kis.firebackend.configuration;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry; 

import com.rabbitmq.client.Connection;
import com.rabbitmq.client.ConnectionFactory;
import reactor.core.scheduler.Schedulers;
import reactor.rabbitmq.RabbitFlux;
import reactor.rabbitmq.Receiver;
import reactor.rabbitmq.ReceiverOptions;
import reactor.rabbitmq.Sender;
import reactor.rabbitmq.SenderOptions;

@Configuration
public class RabbitMQConfiguration 
{
    /**
     * - RABBITMQ_HOST: RabbitMQ host
     * - RABBITMQ_USER: RabbitMQ username
     * - RABBITMQ_PASS: RabbitMQ password
     * - RABBITMQ_PORT: RabbitMQ port
     * - RABBITMQ_EXCHANGE: RabbitMQ exchange name
     */
    @Value("${RABBITMQ_HOST:rabbitmq-service}")
    private String rabbitMQHost;

    @Value("${RABBITMQ_USER:guest}")
    private String username;

    @Value("${RABBITMQ_PASS:guest}")
    private String password;

    @Value("${RABBITMQ_PORT:5672}") 
    private int rabbitMQPort;

    @Value("${RABBITMQ_EXCHANGE:fire-simulation-exchange}")
    private String exchangeName;

    @Bean
    public ConnectionFactory connectionFactory() 
    {
        ConnectionFactory connectionFactory = new ConnectionFactory();

        connectionFactory.setHost(rabbitMQHost);
        connectionFactory.setUsername(username);
        connectionFactory.setPassword(password);
        connectionFactory.setPort(rabbitMQPort);  // Standard AMQP port

        return connectionFactory;
    }

    @Bean
    public Mono<Connection> connectionMono(ConnectionFactory connectionFactory) 
    {
        return Mono.fromCallable(() -> connectionFactory.newConnection("fire-backend-connection"))
            .retryWhen(Retry.backoff(3, Duration.ofSeconds(2))
                .maxBackoff(Duration.ofSeconds(10)))
            .cache();
    } 

    @Bean
    public SenderOptions senderOptions(Mono<Connection> connectionMono) 
    {
        return new SenderOptions()
            .connectionMono(connectionMono)
            .resourceManagementScheduler(Schedulers.boundedElastic());
    }

    @Bean
    public Sender sender(SenderOptions senderOptions) 
    {
        return RabbitFlux.createSender(senderOptions);
    }

    @Bean
    public ReceiverOptions receiverOptions(Mono<Connection> connectionMono) 
    {
        return new ReceiverOptions()
            .connectionMono(connectionMono);
    }

    @Bean
    public Receiver receiver(ReceiverOptions receiverOptions) 
    {
        return RabbitFlux.createReceiver(receiverOptions);
    }

    @Bean
    public String exchangeName()
    {
        return exchangeName;
    }
}
