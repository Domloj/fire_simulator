"""
RabbitMQ Publisher for FFSim — Spec section 5.2.

Publishes telemetry to fire_updates exchange (type: topic) per spec routing keys:
- simulation.telemetry.map.sector_state
- simulation.telemetry.map.sector_state_fast
- simulation.telemetry.sensors.*
- simulation.telemetry.agents.fire_brigade
- simulation.telemetry.agents.forester
"""

import json
import logging
import os
import pika
from typing import Dict, Any, Optional, List
from dataclasses import asdict
from datetime import datetime

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """
    Blocking connection RabbitMQ publisher for deterministic telemetry.
    
    Uses pika.BlockingConnection for simple, reliable publishing.
    Graceful fallback if RabbitMQ unavailable.
    """
    
    EXCHANGE_NAME = "fire_updates"
    EXCHANGE_TYPE = "topic"
    
    def __init__(self,
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 virtual_host: str = "/"):
        """
        Initialize RabbitMQ connection.

        Wartości domyślne brane są ze zmiennych środowiskowych
        (RABBITMQ_HOST/PORT/USER/PASS) — w kontenerze brokerem jest host
        "rabbitmq", nie "localhost". Jawne argumenty mają pierwszeństwo.

        Args:
            host: RabbitMQ host
            port: RabbitMQ port
            username: Credentials
            password: Credentials
            virtual_host: RabbitMQ vhost
        """
        self.host = host or os.environ.get("RABBITMQ_HOST", "localhost")
        self.port = int(port or os.environ.get("RABBITMQ_PORT", 5672))
        username = username or os.environ.get("RABBITMQ_USER", "guest")
        password = password or os.environ.get("RABBITMQ_PASS", "guest")
        self.virtual_host = virtual_host
        self.connection = None
        self.channel = None
        self.available = False
        
        self._connect(username, password)
    
    def _connect(self, username: str, password: str) -> None:
        """
        Establish connection and declare exchange.
        
        Graceful fallback if RabbitMQ unavailable.
        """
        try:
            credentials = pika.PlainCredentials(username, password)
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    virtual_host=self.virtual_host,
                    credentials=credentials,
                    connection_attempts=3,
                    retry_delay=1.0,
                )
            )
            self.channel = self.connection.channel()
            
            # Declare exchange (idempotent). durable=False musi zgadzać się z
            # deklaracją backendu (FFSup), inaczej broker odrzuca redeklarację.
            self.channel.exchange_declare(
                exchange=self.EXCHANGE_NAME,
                exchange_type=self.EXCHANGE_TYPE,
                durable=False
            )
            
            self.available = True
            logger.info("RabbitMQ connected: %s:%d", self.host, self.port)
        
        except Exception as e:
            logger.warning(
                "RabbitMQ connection failed: %s. Telemetry will be queued locally.", e
            )
            self.available = False
    
    def publish(self, routing_key: str, message: Dict[str, Any]) -> bool:
        """
        Publish message to exchange with routing key.
        
        Args:
            routing_key: Topic routing key (e.g., "simulation.telemetry.map.sector_state")
            message: Message body (dict, will be JSON-serialized)
        
        Returns:
            True if published, False if unavailable
        """
        if not self.available or not self.channel:
            logger.debug("RabbitMQ unavailable, skipping publish to %s", routing_key)
            return False
        
        try:
            body = json.dumps(message)
            self.channel.basic_publish(
                exchange=self.EXCHANGE_NAME,
                routing_key=routing_key,
                body=body,
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,  # Persistent
                )
            )
            logger.debug("Published to %s: %d bytes", routing_key, len(body))
            return True
        
        except Exception as e:
            logger.error("Publish failed to %s: %s", routing_key, e)
            self.available = False
            return False
    
    def publish_sector_state(self, sector_data: Dict[str, Any]) -> bool:
        """
        Publish full sector state (spec 5.2.1).
        
        Routing key: simulation.telemetry.map.sector_state
        
        Args:
            sector_data: {sectorId, fireLevel, burnLevel, extinguishLevel, fireState}
        
        Returns:
            True if published
        """
        return self.publish(
            routing_key="simulation.telemetry.map.sector_state",
            message=sector_data
        )
    
    def publish_sector_state_batch(self, sectors_data: List[Dict[str, Any]]) -> bool:
        """
        Publish batch of sector states (all sectors).
        
        Routing key: simulation.telemetry.map.sector_state
        
        Args:
            sectors_data: List of sector dicts
        
        Returns:
            True if published
        """
        for sector_data in sectors_data:
            if not self.publish_sector_state(sector_data):
                return False
        return True
    
    def publish_sector_state_fast(self, 
                                   changed_sectors: List[Dict[str, Any]]) -> bool:
        """
        Publish only changed sectors (spec 5.2.1 fast variant).
        
        Routing key: simulation.telemetry.map.sector_state_fast
        
        Args:
            changed_sectors: List of sectors that changed this tick
        
        Returns:
            True if published
        """
        if not changed_sectors:
            return True  # Nothing to publish
        
        for sector_data in changed_sectors:
            self.publish(
                routing_key="simulation.telemetry.map.sector_state_fast",
                message=sector_data
            )
        return True
    
    def publish_sensor_reading(self, 
                               sensor_type: str,
                               sensor_id: int,
                               location: Dict[str, float],
                               data: Dict[str, Any],
                               timestamp: Optional[str] = None) -> bool:
        """
        Publish sensor reading (spec 5.2.2).
        
        Args:
            sensor_type: WIND_SPEED, WIND_DIRECTION, TEMP_HUMIDITY, etc.
            sensor_id: Unique sensor ID
            location: {lon, lat}
            data: Type-specific sensor data
            timestamp: ISO timestamp (default: now)
        
        Returns:
            True if published
        """
        if not timestamp:
            timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Map sensor type to routing key suffix
        routing_key_map = {
            "WIND_SPEED": "simulation.telemetry.sensors.wind_speed",
            "WIND_DIRECTION": "simulation.telemetry.sensors.wind_direction",
            "TEMP_HUMIDITY": "simulation.telemetry.sensors.temp_humidity",
            "LITTER_MOISTURE": "simulation.telemetry.sensors.litter_moisture",
            "CO2": "simulation.telemetry.sensors.co2",
            "PM2_5": "simulation.telemetry.sensors.pm2_5",
            "CAMERA": "simulation.telemetry.sensors.camera",
        }
        
        routing_key = routing_key_map.get(sensor_type)
        if not routing_key:
            logger.warning("Unknown sensor type: %s", sensor_type)
            return False
        
        message = {
            "sensorId": sensor_id,
            "timestamp": timestamp,
            "sensorType": sensor_type,
            "location": location,
            "data": data,
        }
        
        return self.publish(routing_key=routing_key, message=message)
    
    def publish_fire_brigade_state(self,
                                    brigade_id: int,
                                    state: str,
                                    location: Dict[str, float],
                                    sector_id: Optional[int] = None,
                                    timestamp: Optional[str] = None) -> bool:
        """
        Publish fire brigade state (spec 5.2.3).
        
        Routing key: simulation.telemetry.agents.fire_brigade
        
        Args:
            brigade_id: Fire brigade ID
            state: AVAILABLE, TRAVELLING, EXTINGUISHING
            location: {lon, lat}
            sector_id: Current sector (if any)
            timestamp: ISO timestamp (default: now)
        
        Returns:
            True if published
        """
        if not timestamp:
            timestamp = datetime.utcnow().isoformat() + "Z"
        
        message = {
            "fireBrigadeId": brigade_id,
            "state": state,
            "timestamp": timestamp,
            "location": location,
            "sectorId": sector_id,
        }
        
        return self.publish(
            routing_key="simulation.telemetry.agents.fire_brigade",
            message=message
        )
    
    def publish_fire_brigade_batch(self, 
                                    brigades_data: List[Dict[str, Any]]) -> bool:
        """
        Publish all fire brigades (batch variant, spec 5.2.3).
        
        Routing key: simulation.telemetry.agents.fire_brigade_batch
        
        Args:
            brigades_data: List of brigade states
        
        Returns:
            True if published
        """
        if not brigades_data:
            return True

        # Backend deserializuje to do EvFireBrigadeBatch(List batch) — pole musi
        # nazywać się "batch", inaczej dostaje null i nie emituje pozycji agentów.
        message = {"batch": brigades_data}

        return self.publish(
            routing_key="simulation.telemetry.agents.fire_brigade_batch",
            message=message
        )
    
    def publish_forester_state(self,
                               forester_id: int,
                               state: str,
                               location: Dict[str, float],
                               sector_id: Optional[int] = None,
                               timestamp: Optional[str] = None) -> bool:
        """
        Publish forester patrol state (spec 5.2.3).
        
        Routing key: simulation.telemetry.agents.forester
        
        Args:
            forester_id: Forester patrol ID
            state: AVAILABLE, TRAVELLING, PATROLLING
            location: {lon, lat}
            sector_id: Current sector (if any)
            timestamp: ISO timestamp (default: now)
        
        Returns:
            True if published
        """
        if not timestamp:
            timestamp = datetime.utcnow().isoformat() + "Z"
        
        message = {
            "foresterPatrolId": forester_id,
            "state": state,
            "timestamp": timestamp,
            "location": location,
            "sectorId": sector_id,
        }
        
        return self.publish(
            routing_key="simulation.telemetry.agents.forester",
            message=message
        )
    
    def publish_forester_batch(self,
                                foresters_data: List[Dict[str, Any]]) -> bool:
        """
        Publish all foresters (batch variant, spec 5.2.3).
        
        Routing key: simulation.telemetry.agents.forester_batch
        
        Args:
            foresters_data: List of forester states
        
        Returns:
            True if published
        """
        if not foresters_data:
            return True

        # Backend oczekuje pola "batch" (EvForesterPatrolBatch(List batch)).
        message = {"batch": foresters_data}

        return self.publish(
            routing_key="simulation.telemetry.agents.forester_batch",
            message=message
        )
    
    def close(self) -> None:
        """Close RabbitMQ connection gracefully."""
        if self.connection and not self.connection.is_closed:
            try:
                self.connection.close()
                logger.info("RabbitMQ connection closed")
            except Exception as e:
                logger.error("Error closing RabbitMQ: %s", e)
    
    def __del__(self):
        """Ensure connection is closed on garbage collection."""
        self.close()
