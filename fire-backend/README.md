# Fire Backend

Java/Spring Boot service for core business logic

## Running simulation
In order to start simulation data aggregation and get state on
intervals call POST /run-simulation?interval=<number of seconds> with
configuration as a body payload.

New endpoints:

- POST /simulation/assignBrigades
  - Payload: { "sectorId": <int>, "assignedBrigades": [<int>, ...] }
  - Assigns a list of fire brigade IDs to the sector and forwards the payload to the simulator. The in-memory simulation state is updated immediately, and the assignment will appear in SSE simulation state updates.

