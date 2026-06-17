import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useDispatch, useSelector} from 'react-redux';
import { FormControlLabel, Switch } from '@mui/material';
import { ThunkDispatch } from '@reduxjs/toolkit';
import { AnyAction } from 'redux';

import { RootState } from '../../store/reduxStore';
import { sendBrigadeOrForesterMoveOrder } from '../../store/serverCommunicationReducers';
import { addLog } from '../../store/logsSlice';
import { agentPositionController } from '../../features/maps/AgentPositionController';
import { setAutoApplyEnabled } from '../../store/recommendationSlice';

/* 
* For the time being, this feature is disabled.
* It is not used in the current implementation.
* Should be probably removed... 
*/

// const AUTO_RECOMMENDATION_FEATURE_ENABLED = true;

const AutoRecommendationSwitch: React.FC = () => {
  const [enabled, setEnabled] = useState(false);
  const dispatch: ThunkDispatch<RootState, unknown, AnyAction> = useDispatch();
  const recommendations = useSelector((state: RootState) => state.recommendation.recommendations);
  //  const mapConfiguration = useSelector((state: RootState) => state.mapConfiguration);
  const allRecommendations = useMemo(() => Object.values(recommendations), [recommendations]);

  // const unitTypeMap = useMemo(() => {
  //   const config = mapConfiguration?.configuration;
  //   const map = new Map<number, "brigade" | "forester">();
    
  //   config?.fireBrigades?.forEach((fb: any) => {
  //     map.set(fb.fireBrigadeId, 'brigade');
  //   });
    
  //   config?.foresterPatrols?.forEach((fp: any) => {
  //     map.set(fp.foresterPatrolId, 'forester');
  //   });
    
  //   return map;
  // }, [mapConfiguration?.configuration]);

  // const validSectorIds = useMemo(() => {
  //   const config = mapConfiguration?.configuration;
  //   return new Set((config?.sectors || []).map((s: any) => s.sectorId));
  // }, [mapConfiguration?.configuration]);

  // Get current agent states from configuration
  // const agentStates = useMemo(() => {
  //   const config = mapConfiguration?.configuration;
  //   const states = new Map<number, string>();
    
  //   config?.fireBrigades?.forEach((fb: any) => {
  //     if (fb.fireBrigadeId && fb.state) {
  //       states.set(fb.fireBrigadeId, fb.state);
  //     }
  //   });
    
  //   config?.foresterPatrols?.forEach((fp: any) => {
  //     if (fp.foresterPatrolId && fp.state) {
  //       states.set(fp.foresterPatrolId, fp.state);
  //     }
  //   });
    
  //   return states;
  // }, [mapConfiguration?.configuration]);

  // // Process ALL recommendations, not just one per update
  // const MAX_RECOMMENDATIONS_PER_UPDATE = 10; // Increased to send more recommendations


  const handleToggle = useCallback(() => {
    const newState = !enabled;
    setEnabled(newState);
    dispatch(setAutoApplyEnabled(newState));
    dispatch(addLog({
      text: `[AUTO-APPLY] Toggle changed: ${enabled} -> ${newState}`,
      source: 'simulation',
      level: 'info'
    }));
  }, [enabled, dispatch]);

  useEffect(() => {
    // console.log(`[AutoRecommendationSwitch] useEffect triggered - enabled: ${enabled}, AUTO_RECOMMENDATION_FEATURE_ENABLED: ${AUTO_RECOMMENDATION_FEATURE_ENABLED}, recommendations count: ${allRecommendations.length}`);
    
    // if (!enabled) {
    //   console.log('[AutoRecommendationSwitch] DISABLED - toggle is OFF');
    //   return;
    // }

    // if (!AUTO_RECOMMENDATION_FEATURE_ENABLED) {
    //   console.log('[AutoRecommendationSwitch] DISABLED - global kill-switch is OFF');
    //   return;
    // }

    // if (allRecommendations.length === 0) {
    //   console.log('[AutoRecommendationSwitch] No recommendations available');
    //   return;
    // }

    // console.log(`[AutoRecommendationSwitch] Starting interval - will send recommendations every 1s. Total recommendations: ${allRecommendations.length}`);

    // // Send recommendations every 1 second
    // const intervalId = setInterval(() => {
    //   console.log(`[AutoRecommendationSwitch] Interval tick - processing ${allRecommendations.length} recommendations`);
      
    //   const validRecommendations = allRecommendations
    //     .filter((action) => {
    //       const unitId = Number(action.unitId);
    //       const sectorId = Number(action.sectorId);
          
    //       console.log(`[AutoRecommendationSwitch] Checking recommendation: unitId=${unitId}, sectorId=${sectorId}, unitType=${action.unitType}`);
          
    //       if (!unitId || unitId <= 0 || !sectorId || sectorId <= 0) {
    //         console.log(`[AutoRecommendationSwitch] REJECTED unitId=${unitId}, sectorId=${sectorId} - invalid IDs`);
    //         return false;
    //       }

    //       if (!validSectorIds.has(sectorId)) {
    //         console.log(`[AutoRecommendationSwitch] REJECTED unitId=${unitId}, sectorId=${sectorId} - invalid sector (not in validSectorIds)`);
    //         return false;
    //       }

    //       // Check if we can determine unit type
    //       const unitTypeFromAction = action.unitType;
    //       const hasUnitTypeFromAction = unitTypeFromAction === 'fireBrigade' || unitTypeFromAction === 'foresterPatrol';
    //       const hasUnitTypeFromMap = unitTypeMap.has(unitId);
          
    //       if (!hasUnitTypeFromAction && !hasUnitTypeFromMap) {
    //         console.log(`[AutoRecommendationSwitch] REJECTED unitId=${unitId}, sectorId=${sectorId} - cannot determine unit type (hasUnitTypeFromAction=${hasUnitTypeFromAction}, hasUnitTypeFromMap=${hasUnitTypeFromMap})`);
    //         return false;
    //       }

    //       console.log(`[AutoRecommendationSwitch] ACCEPTED unitId=${unitId}, sectorId=${sectorId}`);
    //       return true;
    //     })
    //     .slice(0, MAX_RECOMMENDATIONS_PER_UPDATE);

    //   console.log(`[AutoRecommendationSwitch] Valid recommendations: ${validRecommendations.length} out of ${allRecommendations.length}`);

    //   if (validRecommendations.length === 0) {
    //     console.log('[AutoRecommendationSwitch] No valid recommendations to send');
    //     return;
    //   }

    //   console.log(`[AutoRecommendationSwitch] Sending ${validRecommendations.length} recommendations (every 1s)`);

    //   // Send ALL orders immediately without delay - backend can handle them
    //   validRecommendations.forEach((action) => {
    //     const unitId = Number(action.unitId);
    //     const sectorId = Number(action.sectorId);
        
    //     // Use unitType from recommendation first, fall back to map lookup
    //     let unitType: "brigade" | "forester" | undefined;
    //     if (action.unitType === 'fireBrigade') {
    //       unitType = 'brigade';
    //     } else if (action.unitType === 'foresterPatrol') {
    //       unitType = 'forester';
    //     } else {
    //       unitType = unitTypeMap.get(unitId);
    //     }

    //     if (!unitType) {
    //       console.warn(`[AutoRecommendationSwitch] Cannot determine unit type for unitId ${unitId}, skipping`);
    //       return;
    //     }

    //     console.log(`[AutoRecommendationSwitch] >>> SENDING ORDER: ${unitType} ${unitId} -> sector ${sectorId}`);
        
    //     // Send immediately - no delay, no throttling for auto-apply
    //     dispatch(
    //       sendBrigadeOrForesterMoveOrder(
    //         unitId,
    //         sectorId,
    //         unitType,
    //         'auto'
    //       )
    //     );
    //   });
    // }, 1000); // Every 1 second

    return () => {
      // console.log('[AutoRecommendationSwitch] Cleaning up interval');
      // clearInterval(intervalId);
    };
  }, [enabled, allRecommendations, dispatch, /* unitTypeMap, validSectorIds*/ ]);

  return (
    <FormControlLabel
      control={
        <Switch
          checked={enabled /* && AUTO_RECOMMENDATION_FEATURE_ENABLED*/ }
          onChange={handleToggle}
          disabled={/* !AUTO_RECOMMENDATION_FEATURE_ENABLED*/ false}
        />
      }
      label="Auto-apply recommendations"
    />
  );
};

export default AutoRecommendationSwitch;
