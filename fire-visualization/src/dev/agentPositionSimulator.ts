import { agentPositionController } from '../features/maps/AgentPositionController';

let intervalId: number | null = null;
let running = false;
let config = { rate: 50, agents: 100 };

const randomBetween = (min: number, max: number) => Math.random() * (max - min) + min;

export function startSimulator(rate = 50, agents = 100) {
  stopSimulator();
  config = { rate, agents };
  running = true;

  // Send `rate` messages per second, evenly split into batches per 100ms
  const batchMs = 100; // every 100ms
  const batchesPerSec = 1000 / batchMs;
  const msgsPerBatch = Math.max(1, Math.round(rate / batchesPerSec));

  intervalId = window.setInterval(() => {
    const now = Date.now();
    const data = [] as any[];
    for (let i = 0; i < msgsPerBatch; i++) {
      // pick random agent id
      const id = Math.floor(Math.random() * agents);
      const lng = randomBetween(19.8, 21.2); // approximate Krakow
      const lat = randomBetween(50.0, 50.5);
      data.push({ id, longitude: lng, latitude: lat, timestamp: new Date().toISOString() });
    }
    // Use parseAndWriteRaw by building raw JSON message to exercise fast-path
    const payload = JSON.stringify({ type: 'agent_position', data });
    agentPositionController.parseAndWriteRaw(payload);
  }, batchMs);
}

export function stopSimulator() {
  if (intervalId != null) {
    clearInterval(intervalId);
    intervalId = null;
  }
  running = false;
}

// Expose on window for quick manual testing
// @ts-ignore
window.__agentPositionSimulator = { startSimulator, stopSimulator };

export function isRunning() { return running; }
