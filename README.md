## Fire Simulation System 

A comprehensive forest fire simulation and visualization system built with microservices architecture.

## Architecture 
The system is built using a microservices architecture with the following components:

* Fire Backend - Java/Spring Boot service for core business logic
* Fire Configuration - Python service for managing simulation configurations
* Fire Simulation - Python-based simulation engine
* Fire Visualization - Frontend application for interactive visualization
* MongoDB - Database for storing configurations and simulation data
* RabbitMQ - Message broker for inter-service communication
* Logging Stack - Grafana, Loki, and Promtail [Work in progress]

### Structure 
```
.
├── docker-compose.yml
├── environments
├── fire-backend
├── fire-configurations
├── fire-simulation
├── fire-visualization
├── logging
├── logs
├── README.md
└── scripts

```
### Environment and Configuration

The frontend now uses OpenStreetMap tiles via MapLibre and does not require Google Maps API keys. If you want to use a custom tile provider, add appropriate configuration in `deployment/fire-visualization/.env` or provide tile URL via environment variables.

### Running services 

To build and start all services at once, run:
```bash
docker compose -f docker-compose.yml up --build     
```

or 

```bash 
docker compose -f docker-compose.yml up --build "rabbitmq-service"  
docker compose -f docker-compose.yml up --build "forest-simulator-service"  
docker compose -f docker-compose.yml up --build "mongo"  
docker compose -f docker-compose.yml up --build "fire-backend-service" 
docker compose -f docker-compose.yml up --build "fire-configuration-service"  
docker compose -f docker-compose.yml up --build "fire-visualization-service"  
```

### Troubleshoting 

* Sometimes `node_module's` requres install with `npm install` 