import { useMemo } from 'react';
import { LineLayer } from '@deck.gl/layers';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { FireBrigade } from '../../model/FireBrigade';
import { ForesterPatrol } from '../../model/ForesterPatrol';

/**
 * Calculate the center point of a sector from its contours
 */
const getSectorCenter = (contours: number[][]): [number, number] | null => {
  if (!contours || contours.length === 0) return null;
  
  let sumLon = 0;
  let sumLat = 0;
  for (const point of contours) {
    sumLon += point[0];
    sumLat += point[1];
  }
  return [sumLon / contours.length, sumLat / contours.length];
};

/**
 * Get destination for an agent based on their state
 */
const getAgentDestination = (
  agent: FireBrigade | ForesterPatrol,
  sectors: any[]
): [number, number] | null => {
  // Only show route if agent is travelling
  if (agent.state !== 'TRAVELLING') {
    return null;
  }

  // Defensive: require currentLocation present
  if (!agent.currentLocation || typeof agent.currentLocation.longitude !== 'number' || typeof agent.currentLocation.latitude !== 'number') {
    return null;
  }

  // If agent has a sectorId, try to find the sector and use its center
  if (agent.sectorId && agent.sectorId > 0) {
    const sector = sectors.find((s: any) => s.sectorId === agent.sectorId);
    if (sector && sector.contours && sector.contours.length > 0) {
      const center = getSectorCenter(sector.contours);
      if (center) {
        // Check if destination is different from current location
        const currentLon = agent.currentLocation.longitude;
        const currentLat = agent.currentLocation.latitude;
        const distance = Math.sqrt(
          Math.pow(center[0] - currentLon, 2) + Math.pow(center[1] - currentLat, 2)
        );
        // Only show route if destination is significantly different (more than 0.001 degrees)
        if (distance > 0.001) {
          return center;
        }
      }
    }
  }

  // Fallback: use base location if it's different from current
  const currentLon = agent.currentLocation.longitude;
  const currentLat = agent.currentLocation.latitude;
  const baseLon = agent.baseLocation?.longitude;
  const baseLat = agent.baseLocation?.latitude;
  if (typeof baseLon !== 'number' || typeof baseLat !== 'number') return null;

  const distance = Math.sqrt(
    Math.pow(baseLon - currentLon, 2) + Math.pow(baseLat - currentLat, 2)
  );
  
  if (distance > 0.001) {
    return [baseLon, baseLat];
  }

  return null;
};

export const useAgentRouteLayer = () => {
  const fireBrigades = useSelector((state: RootState) => state.mapConfiguration.configuration?.fireBrigades || []);
  const foresterPatrols = useSelector((state: RootState) => state.mapConfiguration.configuration?.foresterPatrols || []);
  const sectors = useSelector((state: RootState) => state.mapConfiguration.configuration?.sectors || []);

  const routeLayer = useMemo(() => {
    const routes: Array<{
      path: [[number, number], [number, number]];
      agentType: 'fireBrigade' | 'foresterPatrol';
      agentId: number;
    }> = [];

    // Process Fire Brigades
    fireBrigades.forEach((fb: FireBrigade) => {
      const destination = getAgentDestination(fb, sectors);
      if (destination) {
        routes.push({
          path: [
            [fb.currentLocation.longitude, fb.currentLocation.latitude],
            destination
          ],
          agentType: 'fireBrigade',
          agentId: fb.fireBrigadeId,
        });
      }
    });

    // Process Forester Patrols
    foresterPatrols.forEach((fp: ForesterPatrol) => {
      const destination = getAgentDestination(fp, sectors);
      if (destination) {
        routes.push({
          path: [
            [fp.currentLocation.longitude, fp.currentLocation.latitude],
            destination
          ],
          agentType: 'foresterPatrol',
          agentId: fp.foresterPatrolId,
        });
      }
    });

    if (routes.length === 0) {
      return null; // Return null instead of empty layer
    }

    // Very simple LineLayer configuration - minimal options to avoid WebGL conflicts
    return new LineLayer({
      id: 'agent-route-layer',
      data: routes,
      getSourcePosition: (d: any) => d.path[0],
      getTargetPosition: (d: any) => d.path[1],
      getColor: (d: any) => d.agentType === 'fireBrigade' ? [255, 0, 0, 180] : [0, 0, 255, 180],
      getWidth: 1.5,
      pickable: false,
    });
  }, [fireBrigades, foresterPatrols, sectors]);

  return routeLayer;
};
