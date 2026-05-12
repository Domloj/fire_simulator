#!/bin/bash

set -e 

REPOS=(
  "git@github.com:Fire-Protection-System/fire-backend.git"
  "git@github.com:Fire-Protection-System/fire-configurations.git"
  "git@github.com:Fire-Protection-System/fire-simulation.git"
  "git@github.com:Fire-Protection-System/fire-visualization.git"
)

DIRS=(
  "fire-backend"
  "fire-configurations"
  "fire-simulation"
  "fire-visualization"
)

for i in "${!REPOS[@]}"; do
  if [ -d "${DIRS[$i]}" ]; then
    echo "Updating ${DIRS[$i]}..."
    git -C "${DIRS[$i]}" pull
  else
    echo "Cloning ${DIRS[$i]}..."
    git clone "${REPOS[$i]}" "${DIRS[$i]}"
  fi
done
