import { useEffect } from 'react';
import { agentPositionController } from './AgentPositionController';
import type { Pos } from './AgentPositionController';

// Hook to subscribe to agent position updates without causing React re-renders.
// onFrame will be called on each rAF frame with a Map<number, Pos> snapshot.
export const useAgentPositions = (onFrame: (positions: Map<number, Pos>) => void) => {
  useEffect(() => {
    const unsub = agentPositionController.subscribe(onFrame);
    return () => unsub();
  }, [onFrame]);
};
