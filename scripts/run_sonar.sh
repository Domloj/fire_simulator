#!/bin/bash 
set -euo pipefail

SONAR_HOST_URL="http://127.0.0.1:9000"
SONAR_TOKEN="sqa_03d54ac2e06b975667f54c6ee2f87a205bb314c6"

if [ -z "$SONAR_TOKEN" ]; then
  echo "Error: SONAR_TOKEN environment variable is not set."
  exit 1
fi

docker run --rm \
  --network host \
  -v "$(pwd)/fire-backend:/usr/src" \
  -e SONAR_HOST_URL="$SONAR_HOST_URL" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  sonarsource/sonar-scanner-cli:latest \
  -Dsonar.projectKey=fire-backend \
  -Dsonar.projectName="Fire Backend" \
  -Dsonar.sources=src/main/java \
  -Dsonar.java.binaries=target/classes \
  -Dsonar.java.test.binaries=target/test-classes \
  -Dsonar.host.url="$SONAR_HOST_URL" \
  -Dsonar.token="$SONAR_TOKEN"

docker run --rm \
  --network host \
  -v "$(pwd)/fire-support:/usr/src" \
  -e SONAR_HOST_URL="$SONAR_HOST_URL" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  sonarsource/sonar-scanner-cli:latest \
  -Dsonar.projectKey=fire-support \
  -Dsonar.projectName="Fire Support" \
  -Dsonar.sources=. \
  -Dsonar.host.url="$SONAR_HOST_URL" \
  -Dsonar.token="$SONAR_TOKEN"

docker run --rm \
  --network host \
  -v "$(pwd)/fire-visualization:/usr/src" \
  -e SONAR_HOST_URL="$SONAR_HOST_URL" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  sonarsource/sonar-scanner-cli:latest \
  -Dsonar.projectKey=fire-frontend \
  -Dsonar.projectName="Fire Frontend" \
  -Dsonar.sources=src \
  -Dsonar.host.url="$SONAR_HOST_URL" \
  -Dsonar.token="$SONAR_TOKEN"

docker run --rm \
  --network host \
  -v "$(pwd)/fire-simulation:/usr/src" \
  -e SONAR_HOST_URL="$SONAR_HOST_URL" \
  -e SONAR_TOKEN="$SONAR_TOKEN" \
  sonarsource/sonar-scanner-cli:latest \
  -Dsonar.projectKey=fire-simulation \
  -Dsonar.projectName="Fire Simulation" \
  -Dsonar.sources=. \
  -Dsonar.host.url="$SONAR_HOST_URL" \
  -Dsonar.token="$SONAR_TOKEN"