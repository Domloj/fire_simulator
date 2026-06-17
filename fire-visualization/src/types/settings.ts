export interface SimulationSettings {
  tickInterval: number;
  fireFightersMultiplier: number;
  fireLevelMultiplier: number;
  fireSpreadProbMultiplier: number;
}

export interface SupportSettings {
  recommendationMode: 'heuristic' | 'llm' | 'hybrid';
  agentDecisionMode: 'heuristic' | 'llm' | 'hybrid';
  enableLlmCoordination: boolean;
  enableAgentCommunication: boolean;
}

export interface AppSettings {
  simulation: SimulationSettings;
  support: SupportSettings;
}

export const defaultSettings: AppSettings = {
  simulation: {
    tickInterval: 2.0, // Default to 2s for better performance
    fireFightersMultiplier: 5,
    fireLevelMultiplier: 1,
    fireSpreadProbMultiplier: 0.1,
  },
  support: {
    recommendationMode: 'llm',
    agentDecisionMode: 'llm',
    enableLlmCoordination: true,
    enableAgentCommunication: true,
  },
};

