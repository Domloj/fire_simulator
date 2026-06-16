#!/bin/bash

set -e

check_service() {
    local url=$1
    local name=$2
    curl -s "$url" > /dev/null 2>&1
}

if [ ! -f "pom.xml" ]; then
    echo "Error: Run this script from the fire-backend directory"
    exit 1
fi


FIRE_SIMULATION_DIR="../fire-simulation"
FIRE_SUPPORT_DIR="../fire-support"

start_service() {
    local dir=$1
    local name=$2
    (
        cd "$dir"
        echo "-> Starting $name..."
        set -a && source .local.env && source venv/bin/activate && python main.py &
    ) &
}

wait_for_service() {
    local url=$1
    local name=$2
    local retries=30
    local wait=2
    for i in $(seq 1 $retries); do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "-> $name is up!"
            return 0
        fi
        echo "Waiting for $name... ($i/$retries)"
        sleep $wait
    done
    echo "ERROR: $name did not start in time!"
    exit 1
}

echo "-> Checking prerequisites..."

if ! check_service "http://localhost:15672" "RabbitMQ"; then
    echo "ERROR: RabbitMQ is not running!"
    echo "Start it with: docker compose up rabbitmq-service -d"
    exit 1
else
    echo "-> RabbitMQ is running"
fi

echo "-> Checking MongoDB..."
if ! mongosh --quiet mongodb://127.0.0.1:27017/configurations --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "ERROR: MongoDB is not running!"
    echo "Start it with: docker compose up mongo -d"
    exit 1
else
    echo "-> MongoDB is running"
fi

echo ""

echo "-> Checking Fire Simulation..."
if ! check_service "http://localhost:5000/health" "Fire Simulation"; then
    echo "-> Fire Simulation is not running, starting in background..."
    start_service "$FIRE_SIMULATION_DIR" "Fire Simulation"
    wait_for_service "http://localhost:5000/health" "Fire Simulation"
else
    echo "-> Fire Simulation is running"
fi


echo "-> Checking Fire Support..."
if ! check_service "http://localhost:5001/health" "Fire Support"; then
    echo "-> Fire Support is not running, starting in background..."
    start_service "$FIRE_SUPPORT_DIR" "Fire Support"
    wait_for_service "http://localhost:5001/health" "Fire Support"
else
    echo "-> Fire Support is running"
fi

echo "-> All services are running. Starting integration test..."
./mvnw test -Dtest=LlmPredictionIntegrationTest

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "-> Test completed successfully!"
else
    echo "-> Test finished with errors (code: $TEST_EXIT_CODE)"
fi

exit $TEST_EXIT_CODE
