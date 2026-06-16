import { createSlice, ThunkAction } from '@reduxjs/toolkit';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { AnyAction } from 'redux';
import { Configuration } from '../model/configuration';
import { FireBrigade } from '../model/FireBrigade';
import { ForesterPatrol } from '../model/ForesterPatrol';
import { RootState } from './reduxStore';
import { setConfiguration, updateConfiguration, updateSectorStatesFast, updateSectorAndAgentStatesFast } from './mapConfigurationSlice';
import { updateRecommendation } from './recommendationSlice';
import { API_CONFIG, simulationService } from '../services/api';
import { addLog, addLlmLog } from './logsSlice';
import { agentPositionController } from '../features/maps/AgentPositionController';

/**
 * No idea whats going on here. I feel sorry for everyone who has to read this.
 * This was not written by me and I do not know who wrote it. I do not know how to improve it. 
 * This is one big mess, its working so im not going to touch it. Good luck everyone.
 */

type serverCommunicationState = {
  isFetching: boolean;
  tickInterval: number;
  currentTick: number | null;
};

let abortController = new AbortController();
const initialState: serverCommunicationState = {
  isFetching: false,
  tickInterval: 2.0, // Default to 2s for better performance
  currentTick: null,
};

export const serverCommunicationSlice = createSlice({
  name: 'serverCommunication',
  initialState,
  reducers: {
    abortConnection(state) {
      if (abortController.signal.aborted) {
        return;
      }
      abortController.abort();
      abortController = new AbortController();
      state.isFetching = false;
    },
    setIsFetching(state, action) {
      state.isFetching = action.payload.isFetching;
    },
    setTickInterval(state, action) {
      state.tickInterval = action.payload.tickInterval;
    },
    setCurrentTick(state, action) {
      state.currentTick = action.payload.tick;
    },
  },
});

export type RecommendedAction = {
  unitId: number;
  sectorId: number;
};

export type Recommendation = {
  timestamp: number;
  recommendedActions: RecommendedAction[];
  priority: string;
};

let lastUpdateTime = 0;
let updateCount = 0;                              // number of processed state messages
let totalIncomingMessages = 0;                    // total raw messages received from SSE
let messagesByType: Record<string, number> = {};
let receivedAgentPositionUpdateCount = 0;         // total agent positions received from backend (fast-path count)
let appliedAgentPositionUpdateCount = 0;          // positions applied after throttling
let droppedAgentPositionUpdateCount = 0;          // positions dropped due to throttling
let lastMetricsLog = Date.now();
let lastRecommendationLogTime = 0;
let lastRecommendationHash = '';
let receivedRecommendationCount = 0;
let processedRecommendationCount = 0;
let droppedRecommendationCount = 0;
let lastRecommendationProcessedTime = 0;

// For llm chat logging
let lastLlmChatLogTime = 0;
let lastLlmChatHash = '';
let lastStateUpdateLogTime = 0;
let lastFastSectorUpdateTime = 0;
let lastAgentPositionUpdateTime = 0;

const THROTTLE_MS = 200;                          // ~5fps (200ms)
const RECOMMENDATION_LOG_THROTTLE_MS = 1000;      // Log recommendations at most once per 1 second
const RECOMMENDATION_PROCESS_THROTTLE_MS = 500;   // Process up to ~2 recommendation messages per second
const LLM_CHAT_LOG_THROTTLE_MS = 1000;            // Log LLM chat at most once per 1 second
const STATE_UPDATE_LOG_THROTTLE_MS = 1000;        // Log state updates at most once per 1 second
const FAST_SECTOR_UPDATE_THROTTLE_MS = 50;        // Process fast updates at most once per 50ms (~20fps)


if (typeof window !== 'undefined') {
  // @ts-ignore
  window.__getServerCommMetrics = () => ({
    receivedAgentPositionUpdateCount,
    appliedAgentPositionUpdateCount,
    droppedAgentPositionUpdateCount,
    totalIncomingMessages,
    messagesByType,
    agentFps:   typeof agentPositionController !== 'undefined' ? agentPositionController.getFps() : null,
    bufferSize: typeof agentPositionController !== 'undefined' ? agentPositionController.getBufferSize() : null,
  });
}

const transformSectorData = (sector: any) => ({
  sectorId: sector.sectorId,
  state: {
    temperature:         sector.state?.temperature ?? 0,
    windSpeed:           sector.state?.windSpeed ?? 0,
    windDirection:       sector.state?.windDirection ?? 'NE',
    airHumidity:         sector.state?.airHumidity ?? 0,
    plantLitterMoisture: sector.state?.plantLitterMoisture ?? 0,
    co2Concentration:    sector.state?.co2Concentration ?? 0,
    pm2_5Concentration:  sector.state?.pm2_5Concentration ?? 0,
    fireLevel:           sector.state?.fireLevel ?? 0,
    burnLevel:           sector.state?.burnLevel ?? 0,
    extinguishLevel:     sector.state?.extinguishLevel ?? 0,
    timestamp:           sector.state?.timestamp  ? Date.parse(sector.state.timestamp as any) : 0,
  },
  contours:         sector.contours || [],
  assignedBrigades: sector.assignedBrigades || [],
});

const transformFireBrigadeDataMeta = (fb: any) => ({
  fireBrigadeId: fb.fireBrigadeId,
  action: fb.action || 'EXTINGUISH',
  state: fb.state || 'AVAILABLE',
  sectorId: fb.sectorId || 0,
});

// const transformFireBrigadeDataWithLocation = (fb: any) => ({
//   fireBrigadeId: fb.fireBrigadeId,
//   action: fb.action || 'EXTINGUISH',
//   state: fb.state || 'AVAILABLE',
//   sectorId: fb.sectorId || 0,
//   location: fb.location ?? fb.currentLocation ?? { longitude: 0, latitude: 0 },
// });

const transformForesterPatrolDataMeta = (fp: any) => ({
  foresterPatrolId: fp.foresterPatrolId,
  action: fp.action || 'PATROL',
  state: fp.state || 'AVAILABLE',
  sectorId: fp.sectorId || 0,
});

// const transformForesterPatrolDataWithLocation = (fp: any) => ({
//   foresterPatrolId: fp.foresterPatrolId,
//   action: fp.action || 'PATROL',
//   state: fp.state || 'AVAILABLE',
//   sectorId: fp.sectorId || 0,
//   location: fp.location ?? fp.currentLocation ?? { longitude: 0, latitude: 0 },
// });

function detectMessageFlags(raw: unknown) {
  if (typeof raw !== 'string') {
    return { isFast: false, isRec: false, isAgentPos: false };
  }

  return {
    isFast: raw.includes('"type":"sector_update_fast"'),
    isRec:
      raw.includes('"recommendedActions"') ||
      raw.includes('"recommendation"') ||
      raw.includes('support.recommendations'),
    isAgentPos:
      raw.includes('"type":"agent_position"') ||
      raw.includes('"agent_positions"'),
  };
}

const startSseConnection = (
  configuration: Configuration,
  dispatch: any,
  intervalSeconds: number,
  getState: () => RootState
) => {
  // Store getState in a local variable to ensure it's available in closure
  const getStateFn = getState;
  const runSimulationUrl = `${API_CONFIG.BACKEND_BASE_URL}${API_CONFIG.ENDPOINTS.SIMULATION.RUN}?interval=${intervalSeconds}`;

  fetchEventSource(runSimulationUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', },
    body: JSON.stringify(configuration),
    signal: abortController.signal,
    openWhenHidden: true,

    onopen: async (response: Response): Promise<void> => {
      if (!response.ok) {
        // console.error('[Simulation] SSE connection failed:', response.status, response.statusText);
      } else {
        dispatch(serverCommunicationSlice.actions.setIsFetching({ isFetching: true }));
        dispatch(startLLMChatStream() as any);
      }
    },

    onmessage: (event) => {
      try {
        let isFastUpdate = false;
        let isRecommendation = false;
        let isAgentPosition = false;
        try {
          const rawData = event.data;
          if (typeof rawData === 'string') {
            if (rawData.includes('"type":"sector_update_fast"')) {
              isFastUpdate = true;
            }
            if (rawData.includes('"recommendedActions"') || rawData.includes('"recommendation"') || rawData.includes('support.recommendations')) {
              isRecommendation = true;
              receivedRecommendationCount++;
            }
            if (rawData.includes('"type":"agent_position"') || rawData.includes('"agent_positions"')) {
              isAgentPosition = true;
              receivedAgentPositionUpdateCount++;

              try {
                totalIncomingMessages++;
                messagesByType['agent_position'] = (messagesByType['agent_position'] || 0) + 1;
                const handled = agentPositionController.parseAndWriteRaw(rawData);
                if (handled) {
                  return;
                }
              } catch (e) {
                // fall through to normal parsing if fast path fails
              }
            }
          }
        } catch (e) {
          // If quick check fails, proceed with normal throttling
        }

        const now = Date.now();
        if (isFastUpdate) {
          if (now - lastFastSectorUpdateTime < FAST_SECTOR_UPDATE_THROTTLE_MS) {
            return;
          }
          lastFastSectorUpdateTime = now;
        } else if (isRecommendation) {
          if (now - lastRecommendationProcessedTime < RECOMMENDATION_PROCESS_THROTTLE_MS) {
            droppedRecommendationCount++;
            const timeSinceLastLog = now - lastRecommendationLogTime;
            if (timeSinceLastLog >= RECOMMENDATION_LOG_THROTTLE_MS) {
              lastRecommendationLogTime = now;
              dispatch(addLog({
                text: `[Perf] Recommendation message throttled (recent). recv:${receivedRecommendationCount} processed:${processedRecommendationCount} dropped:${droppedRecommendationCount}`,
                source: 'simulation',
                level: 'warn'
              }));
            }
            return;
          }
          lastRecommendationProcessedTime = now;
          processedRecommendationCount++;
        } else {
          // Throttle normal updates
          if (now - lastUpdateTime < THROTTLE_MS) {
            return; // Reject message before expensive JSON parsing
          }
          lastUpdateTime = now;
        }

        const parsedData = JSON.parse(event.data);

        // Fast-path: forward agent arrays to AgentPositionController
        try {
          const data = parsedData.type === 'state' ? parsedData.data : parsedData;
          if (Array.isArray(data?.fireBrigades) && data.fireBrigades.length > 0) {
            agentPositionController.writeBatch(data.fireBrigades);
          }
          if (Array.isArray(data?.foresterPatrols) && data.foresterPatrols.length > 0) {
            agentPositionController.writeBatch(data.foresterPatrols);
          }
        } catch (e) {
          // ignore
        }

        // Check if this is an LLM message
        if (parsedData.type === 'llm' && parsedData.data) {
          const llmData = parsedData.data;
          const typeLabel = llmData.type === 'llm_request' ? 'REQUEST' :
            llmData.type === 'llm_response' ? 'RESPONSE' :
              llmData.type === 'llm_insight' ? 'INSIGHT' : 'LLM';
          const agentLabel = llmData.agent || 'Unknown';
          const sectorLabel = llmData.sectorId ? `Sector ${llmData.sectorId}` : '';

          dispatch(addLlmLog({
            text: `[LLM] [${typeLabel}] [${agentLabel}] ${sectorLabel ? `[${sectorLabel}] ` : ''}${llmData.message || ''}`,
            source: 'llm',
            level: 'info'
          }));
          return;
        }

        if (parsedData.type === 'llm_chat' && parsedData.data) {
          const chatData = parsedData.data;
          const agentId = chatData.agentId || chatData.source || 'System';
          const type = chatData.type || 'Chat';

          const now = Date.now();
          const timeSinceLastLog = now - lastLlmChatLogTime;

          const messageHash = `${type}:${agentId}:${chatData.description || ''}:${chatData.sectorId || ''}`;
          const messageChanged = messageHash !== lastLlmChatHash;

          const isImportant = type === 'system_event' || type === 'LLM_proposition';
          const shouldLog = isImportant || (messageChanged && timeSinceLastLog >= LLM_CHAT_LOG_THROTTLE_MS);

          if (shouldLog) {
            lastLlmChatLogTime = now;
            lastLlmChatHash = messageHash;

            let logText = '';
            let level: 'info' | 'warn' | 'error' = 'info';

            if (type === 'LLM_proposition') {
              const prop = chatData.content;
              let desc = '';
              if (typeof prop === 'object' && prop !== null) {
                desc = prop.proposition || prop.reasoning || JSON.stringify(prop);
              } else {
                desc = prop || 'No message';
              }
              logText = `[STRATEGY] Coordinator: ${desc}`;
              level = 'info';
            } else if (type === 'CoordinatorResponse') {
              const desc = chatData.description || (chatData.content?.proposition) || "Response from coordinator";
              logText = `[COORDINATOR] ${agentId}: ${desc}`;
              level = 'info';
            } else if (type === 'BrigadeOrder') {
              logText = `[AGENT] ${agentId}: ${chatData.description || "Moving to target"}`;
            } else if (type === 'AgentReasoning') {
              logText = `[AGENT-THINK] ${agentId}: ${chatData.description}`;
              level = 'info';
            } else if (type === 'AgentProposition') {
              logText = `[AGENT-PROP] ${agentId}: ${chatData.description}`;
              level = 'info';
            } else if (type === 'system_event') {
              logText = `[SYSTEM] ${chatData.description}`;
              level = chatData.level || 'info';
            } else {
              const action = chatData.action ? `${chatData.action} ` : '';
              const sector = chatData.sectorId ? `@ Sec ${chatData.sectorId} ` : '';
              logText = `[CHAT] [${agentId}] ${action}${sector}${chatData.description || ''}`;
            }

            dispatch(addLlmLog({ text: logText, source: 'llm', level }));
          }
          return;
        }

        // MCTS Update logging disabled to reduce chat pollution
        /*
        if (parsedData.recommendedActions && Array.isArray(parsedData.recommendedActions)) {
           if (parsedData.tick % 10 === 0 && parsedData.recommendedActions.length > 0) {
              dispatch(addLlmLog({
                text: `[REC] MCTS Update: ${parsedData.recommendedActions.length} active recommendations`,
                source: 'llm',
                level: 'info'
              }));
           }
        }
        */

        if (parsedData.type === 'sector_update_fast') {
          const sectors = parsedData.sectors || parsedData.data?.sectors;
          if (sectors) {
            dispatch(updateSectorStatesFast({ sectorUpdates: sectors }));
            return;
          }
        }

        const stateData = parsedData.type === 'state' ? parsedData.data : parsedData;

        if (typeof stateData.tick === 'number') {
          dispatch(serverCommunicationSlice.actions.setCurrentTick({ tick: stateData.tick }));
        }

        if (abortController.signal.aborted) {
          return;
        }

        if (stateData) {
          updateCount++;
          const agentCount = (stateData.fireBrigades?.length || 0) + (stateData.foresterPatrols?.length || 0);
          receivedAgentPositionUpdateCount += agentCount; // received from backend

          // For high-frequency agent positions we now use AgentPositionController.
          const nowTs = Date.now();
          const SNAPSHOT_INTERVAL_MS = 1000; // 1s
          let includeAgents = false;
          if (nowTs - lastAgentPositionUpdateTime >= SNAPSHOT_INTERVAL_MS) {
            includeAgents = true;
            lastAgentPositionUpdateTime = nowTs;
          }

          const timestamp = stateData.timestamp
            ? (typeof stateData.timestamp === 'string' ? stateData.timestamp : new Date(stateData.timestamp).toISOString())
            : new Date().toISOString();

          const configurationUpdate = {
            forestName: stateData.forestName || '',
            timestamp,
            sectors: (stateData.sectors || []).map(transformSectorData),
            fireBrigades: (stateData.fireBrigades || []).map(transformFireBrigadeDataMeta),
            foresterPatrols: (stateData.foresterPatrols || []).map(transformForesterPatrolDataMeta),
          };

          if (includeAgents) {
            try {
              const controller = require('../features/maps/AgentPositionController').agentPositionController;
              const positions = controller.getPositionsSnapshot();
              const hasValidLocation = (loc: any) => loc && !(Math.abs(loc.longitude) < 1e-6 && Math.abs(loc.latitude) < 1e-6);

              configurationUpdate.fireBrigades = configurationUpdate.fireBrigades.map((fb: any) => {
                const loc = fb.location ?? fb.currentLocation ?? { longitude: 0, latitude: 0 };
                if (!hasValidLocation(loc)) {
                  const pos = positions.get(`fireBrigade:${fb.fireBrigadeId}`);
                  if (pos) return { ...fb, location: { longitude: pos.lng, latitude: pos.lat } };
                }
                return fb;
              });

              configurationUpdate.foresterPatrols = configurationUpdate.foresterPatrols.map((fp: any) => {
                const loc = fp.location ?? fp.currentLocation ?? { longitude: 0, latitude: 0 };
                if (!hasValidLocation(loc)) {
                  const pos = positions.get(`foresterPatrol:${fp.foresterPatrolId}`);
                  if (pos) return { ...fp, location: { longitude: pos.lng, latitude: pos.lat } };
                }
                return fp;
              });
            } catch (e) {
              // ignore
            }
          }

          const totalAgentsThisMessage = (stateData.fireBrigades?.length || 0) + (stateData.foresterPatrols?.length || 0);
          if (includeAgents) {
            appliedAgentPositionUpdateCount += totalAgentsThisMessage;
          } else {
            droppedAgentPositionUpdateCount += totalAgentsThisMessage;
          }

          dispatch(updateConfiguration({ configurationUpdate }));

          const now = Date.now();
          if (now - lastStateUpdateLogTime >= STATE_UPDATE_LOG_THROTTLE_MS) {
            lastStateUpdateLogTime = now;
            const tick = stateData.tick ?? '?';
            dispatch(addLog({
              text: `[Tick ${tick}] State update — sectors:${configurationUpdate.sectors?.length ?? 0}, FB:${configurationUpdate.fireBrigades?.length ?? 0}, FP:${configurationUpdate.foresterPatrols?.length ?? 0}`,
              source: 'simulation',
              level: 'info'
            }));
          }
        }

        if (stateData.timestamp && stateData.recommendedActions) {
          const transformedActions = (stateData.recommendedActions || []).map((action: any) => {
            const unitType = (action.unitType === 'fireBrigade' || action.unitType === 'foresterPatrol') 
              ? action.unitType 
              : undefined;

            const unitId = String(action.unitId ?? action.fireBrigadeId ?? '');
            const sectorId = String(action.sectorId ?? '');
            const actionLabel = (action.actionType || 'MOVE').toString().toUpperCase();
            const label = unitType === 'foresterPatrol' ? `FP_${unitId.padStart(3, '0')}` : `FB_${unitId.padStart(3, '0')}`;
            const description = `${actionLabel} ${label} -> sector ${sectorId}`;

            return {
              unitId,
              sectorId,
              description,
              unitType,
              actionType: action.actionType,
            };
          });

          const timestamp = stateData.timestamp
            ? (typeof stateData.timestamp === 'string' ? stateData.timestamp : new Date(stateData.timestamp).toISOString())
            : new Date().toISOString();

          dispatch(updateRecommendation({
            timestamp,
            recommendedActions: transformedActions,
            priority: stateData.priority || "normal"
          }));

          // Auto-apply: If toggle is ON, send all orders immediately
          if (getStateFn().recommendation.autoApplyEnabled && transformedActions.length > 0) {
            transformedActions.forEach((action: any) => {
              const unitId = Number(action.unitId);
              const sectorId = Number(action.sectorId);
              
              if (unitId > 0 && sectorId > 0) {
                const unitType = action.unitType === 'fireBrigade' ? 'brigade' : 
                                action.unitType === 'foresterPatrol' ? 'forester' : undefined;
                if (unitType) {
                  dispatch(sendBrigadeOrForesterMoveOrder(unitId, sectorId, unitType, 'auto'));
                }
              }
            });
          }


          try {
            const now = Date.now();
            const timeSinceLastLog = now - lastRecommendationLogTime;

            const currentHash = transformedActions.map((a: any) =>
              `${a.unitType}:${a.unitId}:${a.sectorId}:${a.actionType}`
            ).sort().join('|');

            const recommendationsChanged = currentHash !== lastRecommendationHash;
            const shouldLog = recommendationsChanged && timeSinceLastLog >= RECOMMENDATION_LOG_THROTTLE_MS;

            if (shouldLog) {
              lastRecommendationLogTime = now;
              lastRecommendationHash = currentHash;

              const recCount = transformedActions.length;
              const brigadeLabel = (id: string) => `Fire Brigade [FB_${id.padStart(3, '0')}]`;
              const patrolLabel = (id: string) => `Forester Patrol [FP_${id.padStart(3, '0')}]`;
              const actionText = (a: any) => (a.actionType?.toUpperCase() || 'MOVE');

              const brigades = transformedActions
                .filter((a: any) => a.unitType === 'fireBrigade')
                .map((a: any) => `  - ${brigadeLabel(a.unitId)} -> ${actionText(a)} -> [Sector ${a.sectorId}]`)
                .join('\n');
              const patrols = transformedActions
                .filter((a: any) => a.unitType === 'foresterPatrol')
                .map((a: any) => `  - ${patrolLabel(a.unitId)} -> ${actionText(a)} -> [Sector ${a.sectorId}]`)
                .join('\n');

              const lines = [
                `[Tick ${stateData.tick ?? '?'}] Recommendations (${recCount})`,
                '[Fire Brigades]:',
                brigades || '  - none',
                '[Forest Patrols]:',
                patrols || '  - none',
                '------------------------------------------------------------------',
              ].join('\n');

              dispatch(addLog({ text: lines, source: 'simulation', level: 'info' }));
            }
          } catch (e) {
            // ignore log errors
          }
        }

      } catch (parseError) {
        // console.error('[Simulation] Failed to parse event data:', parseError, event.data);
      }
    },
    onerror: (error) => {
      const isBrokenPipe = error?.message?.includes('Broken pipe') ||
        error?.message?.includes('Connection closed') ||
        error?.name === 'AbortError';

      if (!isBrokenPipe) {
        // console.error('[Simulation] SSE error:', error);
      } else {
        // console.log('[Simulation] SSE connection interrupted, will retry...'); // Disabled for performance
      }
    },
    onclose: () => {
      dispatch(stopLLMChatStream() as any);
      if (abortController.signal.aborted) {
        dispatch(serverCommunicationSlice.actions.setIsFetching({ isFetching: false }));
      }
    }
  });
};

export const startFetchingConfigurationUpdate = (): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any, getState: () => RootState) => {
    const state = getState();
    const { serverCommunication, mapConfiguration } = state;
    if (serverCommunication.isFetching) {
      return;
    }

    let configurationToUse: Configuration = JSON.parse(JSON.stringify(mapConfiguration.configuration));
    let shouldSendRequest = true;

    try {
      const snapshot = await simulationService.getSnapshot();
      const snapshotData = snapshot?.snapshot;
      if (snapshot?.status === 'ok' && snapshotData?.running && snapshotData?.config) {
        configurationToUse = snapshotData.config;
        shouldSendRequest = false;
        dispatch(setConfiguration({ configuration: configurationToUse }));
        if (typeof snapshotData.tick === 'number') {
          dispatch(serverCommunicationSlice.actions.setCurrentTick({ tick: snapshotData.tick }));
        }
      }
    } catch (error) {
      // ignore snapshot errors; fallback to normal start
    }

    configurationToUse.sectors.forEach((sector: any) => {
      if (sector.assignedBrigades && sector.assignedBrigades.length > 0) {
        sector.assignedBrigades = sector.assignedBrigades.map((b: any) => Number(b));
      }
    });

    if (shouldSendRequest) {
      try {
        await simulationService.sendSimulationRequest(configurationToUse);
      } catch (error) {
        dispatch(serverCommunicationSlice.actions.setIsFetching({ isFetching: false }));
        return;
      }
    }

    dispatch(serverCommunicationSlice.actions.setIsFetching({ isFetching: true }));

    const intervalSeconds = serverCommunication.tickInterval ?? 2.0; // Default to 2s for better performance
    startSseConnection(configurationToUse, dispatch, intervalSeconds, getState);
  };
};

export const resumeSimulationIfRunning = (): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any, getState: () => RootState) => {
    const state = getState();
    const { serverCommunication } = state;
    if (serverCommunication.isFetching) {
      return;
    }

    try {
      const snapshot = await simulationService.getSnapshot();
      const snapshotData = snapshot?.snapshot;
      if (snapshot?.status !== 'ok' || !snapshotData?.running || !snapshotData?.config) {
        return;
      }

      dispatch(setConfiguration({ configuration: snapshotData.config }));
      if (typeof snapshotData.tick === 'number') {
        dispatch(serverCommunicationSlice.actions.setCurrentTick({ tick: snapshotData.tick }));
      }

      dispatch(serverCommunicationSlice.actions.setIsFetching({ isFetching: true }));

      const intervalSeconds = serverCommunication.tickInterval ?? 2.0; // Default to 2s for better performance
      startSseConnection(snapshotData.config, dispatch, intervalSeconds, getState);
    } catch (error) {
      // ignore resume errors
    }
  };
};

export const sendStopRequest = (): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any, getState: () => RootState) => {
    const state = getState();
    const { serverCommunication } = state;
    if (serverCommunication.isFetching == false) {
      return;
    }
    dispatch(serverCommunicationSlice.actions.setIsFetching({ isFetching: false }));

    try {
      await simulationService.stopSimulation();
    } catch (error) {
      // ignore stop errors
    }
  }
}

function getRandomIntInclusive(min: number, max: number) {
  const low = Math.min(min, max);
  const high = Math.max(min, max);

  return Math.random() * (high - low) + low;
}

export const sendBrigadeOrForesterMoveOrder = (unitId: number, targetSectorId: number, type: "brigade" | "forester", source: string = 'ui'): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any, getState: () => RootState) => {
    const state = getState();
    const { mapConfiguration } = state;

    if (!targetSectorId || targetSectorId <= 0) {
      return;
    }

    const targetSector = mapConfiguration.configuration.sectors.find((sector) => sector.sectorId === targetSectorId);

    if (!targetSector) {
      return;
    }

    const getRandomPositionInSector = (contours: number[][]): { longitude: number, latitude: number } => {
      const minLon = Math.min(contours[0][0], contours[1][0], contours[2][0], contours[3][0]);
      const maxLon = Math.max(contours[0][0], contours[1][0], contours[2][0], contours[3][0]);
      const minLat = Math.min(contours[0][1], contours[1][1], contours[2][1], contours[3][1]);
      const maxLat = Math.max(contours[0][1], contours[1][1], contours[2][1], contours[3][1]);

      const marginLon = (maxLon - minLon) * 0.1;
      const marginLat = (maxLat - minLat) * 0.1;

      return {
        longitude: getRandomIntInclusive(minLon + marginLon, maxLon - marginLon),
        latitude: getRandomIntInclusive(minLat + marginLat, maxLat - marginLat),
      };
    };

    const targetPosition = getRandomPositionInSector(targetSector.contours);

    try {
      const payload = {
        [type == "brigade" ? "fireBrigadeId" : "foresterPatrolId"]: unitId,
        goingToBase: false,
        location: targetPosition,
        action: type === "brigade" ? "EXTINGUISH" : "PATROL",
        source: source
      };

      dispatch(addLog({ text: `[Simulation] Sending ${type} order (source=${source}): unit=${unitId} -> sector=${targetSectorId}`, source: 'simulation', level: 'info' }));

      if (type === "brigade") {
        await simulationService.orderFireBrigade(payload);
      } else {
        await simulationService.orderForestPatrol(payload);
      }
    } catch (err) {
      // ignore order errors
    }
  }
}

export const sendBrigadeOrForesterMoveToBaseOrder = (brigadeID: number, type: "brigade" | "forester"): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any, getState: () => RootState) => {
    const state = getState();
    const { mapConfiguration } = state;

    let unit: ForesterPatrol | FireBrigade | undefined;

    if (type == "brigade") {
      unit = mapConfiguration.configuration.fireBrigades.find((fireBrigade) => fireBrigade.fireBrigadeId === brigadeID);
    } else {
      unit = mapConfiguration.configuration.foresterPatrols.find((foresterPatrol) => foresterPatrol.foresterPatrolId === brigadeID);
    }

    if (!unit) {
      // console.warn(`[Simulation] ${type} ${brigadeID} not found`);
      return;
    }

    try {
      const payload = {
        [type == "brigade" ? "fireBrigadeId" : "foresterPatrolId"]: brigadeID,
        goingToBase: true,
        location: {
          longitude: unit.baseLocation.longitude,
          latitude: unit.baseLocation.latitude
        }
      };

      if (type === "brigade") {
        await simulationService.orderFireBrigade(payload);
      } else {
        await simulationService.orderForestPatrol(payload);
      }
    } catch (err) {
      // ignore order errors
    }
  }
}

export const setSimulationSpeed = (tickInterval: number): ThunkAction<void, RootState, unknown, AnyAction> => {
  /* 
  * Disabled due to backend limitations - changing tick interval during simulation is not supported.
  */

  return async (dispatch: any, getState: () => RootState) => { }

  // return async (dispatch: any) => {
  //   // Allow down to 0.1s (100ms) for UI updates
  //   const clamped = Math.max(0.1, Math.min(30, tickInterval));
  //   dispatch(serverCommunicationSlice.actions.setTickInterval({ tickInterval: clamped }));

  //   try {
  //     await simulationService.setSimulationSpeed(clamped);
  //   } catch (err) {
  //     console.error('[Simulation] Failed to set simulation speed:', err);
  //   }
  // };
};

let llmChatCleanup: (() => void) | null = null;

export const startLLMChatStream = (): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any) => {
    // Stop previous stream if exists
    if (llmChatCleanup) {
      llmChatCleanup();
      llmChatCleanup = null;
    }

    llmChatCleanup = simulationService.streamLLMChat(
      (msg: any) => {
        // Convert LLM message to chat log format
        const agentId = msg.agentId || 'Unknown';
        const type = msg.type || 'Chat';
        let logText = '';
        let level: 'info' | 'warn' | 'error' = 'info';

        if (type === 'BrigadeOrder') {
          logText = `[AGENT] ${agentId}: ${msg.description}`;
        } else if (type === 'AgentReasoning') {
          logText = `[REASONING] ${agentId}: ${msg.description}`;
        } else if (type === 'AgentProposition') {
          logText = `[AGENT-PROP] ${agentId}: ${msg.description}`;
        } else if (type === 'CoordinatorResponse') {
          const desc = msg.description || msg.content?.proposition;
          logText = `[COORDINATOR] ${agentId}: ${desc}`;
        } else {
          logText = `[LLM] [${type}] ${agentId}: ${msg.description}`;
        }

        dispatch(addLlmLog({
          text: logText,
          source: 'llm',
          level: level
        }));
      },
      (err: any) => {
        // console.error('[LLM Chat] Stream error:', err);
        dispatch(addLlmLog({
          text: '[LLM CHAT] Stream disconnected',
          source: 'llm',
          level: 'warn'
        }));
      }
    );

    dispatch(addLlmLog({
      text: '[LLM CHAT] Stream connected',
      source: 'llm',
      level: 'info'
    }));
  };
};

export const stopLLMChatStream = (): ThunkAction<void, RootState, unknown, AnyAction> => {
  return async (dispatch: any) => {
    if (llmChatCleanup) {
      llmChatCleanup();
      llmChatCleanup = null;
      dispatch(addLlmLog({
        text: '[LLM CHAT] Stream disconnected',
        source: 'llm',
        level: 'info'
      }));
    }
  };
};

export const {
  abortConnection
} = serverCommunicationSlice.actions;
export const { reducer: serverCommunicationReducer } = serverCommunicationSlice;
