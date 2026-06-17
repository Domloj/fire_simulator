/**
 * API Configuration
 * Centralized configuration for all API endpoints
 */

const getBackendUrl = (): string => {
  const envUrl = typeof window !== 'undefined' && (window as any).__ENV__?.FIRE_BACKEND_SERVICE
    ? (window as any).__ENV__.FIRE_BACKEND_SERVICE
    : typeof process !== 'undefined' && process.env?.FIRE_BACKEND_SERVICE
    ? process.env.FIRE_BACKEND_SERVICE
    : '';
  
  if (envUrl) {
    if (!envUrl.startsWith('http')) {
      return `http://${envUrl}:8181`;
    }
    return envUrl;
  }
  
  return 'http://localhost:8181';
};

const getConfigurationServiceUrl = (): string => {
  const envUrl = typeof window !== 'undefined' && (window as any).__ENV__?.FIRE_CONFIGURATION_SERVICE
    ? (window as any).__ENV__.FIRE_CONFIGURATION_SERVICE
    : typeof process !== 'undefined' && process.env?.FIRE_CONFIGURATION_SERVICE
    ? process.env.FIRE_CONFIGURATION_SERVICE
    : '';
  
  if (envUrl) {
    if (!envUrl.startsWith('http')) {
      return `http://${envUrl}:31415`;
    }
    return envUrl;
  }
  
  return 'http://localhost:31415';
};

export const API_CONFIG = {
  BACKEND_BASE_URL: getBackendUrl(),
  CONFIGURATION_BASE_URL: getConfigurationServiceUrl(),
  ENDPOINTS: {
    // Simulation endpoints
    SIMULATION: {
      SEND_REQUEST: '/simulation/send-simulation-request',
      RUN: '/simulation/run-simulation',
      SNAPSHOT: '/simulation/snapshot',
      STOP: '/simulation/stop-simulation',
      PAUSE: '/simulation/pause',
      RESUME: '/simulation/resume',
      STEP: '/simulation/step',
      STEP_BACK: '/simulation/step-back',
      SET_SPEED: '/simulation/set-speed',
      LLM_MODE: '/simulation/llm-mode',
      ORDER_FIRE_BRIGADE: '/simulation/orderFireBrigade',
      ORDER_FOREST_PATROL: '/simulation/orderForestPatrol',
      ASSIGN_BRIGADES: '/simulation/assignBrigades',
    },
    // Configuration service endpoints
    CONFIGURATION: {
      NODES: '/api/v1/nodes',
      NODE_BY_ID: (id: string) => `/api/v1/nodes/${id}`,
      NODE_CHILDREN: (id: string) => `/api/v1/nodes/${id}/children`,
    },
  },
} as const;
