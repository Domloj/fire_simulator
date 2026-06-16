/**
 * Simulation Service API
 * Handles all simulation-related API calls and SSE connections
 */

import { httpClient } from './httpClient';
import { API_CONFIG } from './config';
import { Configuration } from '../../model/configuration';

const baseUrl = API_CONFIG.BACKEND_BASE_URL;

export interface SimulationOrder {
  fireBrigadeId?: number;
  foresterPatrolId?: number;
  goingToBase: boolean;
  location: {
    longitude: number;
    latitude: number;
  };
}

export interface LLMChatMessage {
  agentId: string;
  type: string;
  action: string;
  sectorId?: number;
  priority?: number;
  description: string;
  timestamp: string;
  status: string;
  content?: any;
  source: string;
}

export const simulationService = {
  /**
   * Send simulation request
   */
  sendSimulationRequest: async (configuration: Configuration): Promise<void> => {
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.SEND_REQUEST}`,
      configuration
    );
  },

  /**
   * Get simulation snapshot (if running)
   */
  getSnapshot: async (): Promise<any> => {
    const response = await httpClient.get(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.SNAPSHOT}`
    );
    return response.data;
  },

  /**
   * Stop simulation
   */
  stopSimulation: async (): Promise<void> => {
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.STOP}`,
      {}
    );
  },

  /**
   * Toggle LLM-driven recommendation mode in support service.
   * When enabled=true, support will run in pure LLM mode (no MCTS).
   */
  setLlmMode: async (enabled: boolean): Promise<void> => {
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.LLM_MODE}`,
      { enabled }
    );
  },

  /**
   * Set simulation speed
   */
  setSimulationSpeed: async (tickInterval: number): Promise<void> => {
    // Allow floating point values for ultra-smooth movement
    const clamped = Math.max(0.01, Math.min(30, tickInterval));
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.SET_SPEED}?tickInterval=${clamped}`,
      { tickInterval: clamped }
    );
  },

  /**
   * Order fire brigade movement
   */
  orderFireBrigade: async (order: SimulationOrder): Promise<void> => {
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.ORDER_FIRE_BRIGADE}`,
      order
    );
  },

  /**
   * Order forest patrol movement
   */
  orderForestPatrol: async (order: SimulationOrder): Promise<void> => {
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.ORDER_FOREST_PATROL}`,
      order
    );
  },

  /**
   * Assign brigades to sectors
   */
  assignBrigades: async (data: unknown): Promise<void> => {
    await httpClient.post(
      `${baseUrl}${API_CONFIG.ENDPOINTS.SIMULATION.ASSIGN_BRIGADES}`,
      data
    );
  },

  /**
   * Stream LLM chat messages via SSE
   */
  streamLLMChat: (onMessage: (msg: LLMChatMessage) => void, onError: (err: any) => void): (() => void) => {
    const eventSource = new EventSource(`${baseUrl}/simulation/llm-chat`);
    
    eventSource.addEventListener('message', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (err) {
        console.error('Failed to parse LLM chat message:', err);
      }
    });

    eventSource.addEventListener('error', (event: Event) => {
      console.error('LLM chat stream error:', event);
      onError(event);
      eventSource.close();
    });

    // Return cleanup function
    return () => {
      eventSource.close();
    };
  },
};
