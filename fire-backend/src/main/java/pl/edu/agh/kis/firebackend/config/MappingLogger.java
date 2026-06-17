package pl.edu.agh.kis.firebackend.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@Component
public class MappingLogger 
{
    private static final Logger log = LoggerFactory.getLogger(MappingLogger.class);

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping mapping;

    @EventListener(ApplicationReadyEvent.class)
    public void logMappings() 
    {
        log.info("Listing registered request mappings:");

        mapping.getHandlerMethods().forEach((key, value) ->
            log.info("{} => {}#{}", key, value.getBeanType().getSimpleName(), value.getMethod().getName())
        );
    }
}
