import { Box, Divider, Typography, List, ListItem, Button } from '@mui/material';
import { useSelector, useDispatch } from 'react-redux';
import { ThunkDispatch } from '@reduxjs/toolkit';
import { AnyAction } from 'redux';
import { useCallback, useMemo } from 'react';

import { RootState } from '../../store/reduxStore';
import { sendBrigadeOrForesterMoveOrder } from "../../store/serverCommunicationReducers";

const RecommendedDecisions = () => {
  const dispatch: ThunkDispatch<RootState, unknown, AnyAction> = useDispatch();
  const recommendations = useSelector((state: RootState) => state.recommendation.recommendations);
  const mapConfiguration = useSelector((state: RootState) => state.mapConfiguration);
  
  const allRecommendations = useMemo(() => Object.values(recommendations), [recommendations]);

  const handleApplyRecommendation = useCallback((unitId: number, sectorId: number, unitTypeHint?: 'fireBrigade' | 'foresterPatrol') => {
    // Validate inputs
    if (!unitId || unitId <= 0) {
      console.warn('[RecommendedDecisions] Invalid unit ID:', unitId);
      return;
    }
    
    if (!sectorId || sectorId <= 0) {
      console.warn('[RecommendedDecisions] Invalid sector ID:', sectorId);
      return;
    }
    
    const config = mapConfiguration?.configuration;
    const sectorIds = new Set((config?.sectors || []).map((s: any) => s.sectorId));
    if (!sectorIds.has(sectorId)) {
      console.warn(`[RecommendedDecisions] Sector ${sectorId} not found in configuration. Available: [${Array.from(sectorIds).join(', ')}]. Skipping recommendation for unit ${unitId}.`);
      return;
    }
    
    // Determine if unitId is a fire brigade or forester patrol (prefer explicit unitType from recommendation)
    const isFireBrigade = unitTypeHint === 'fireBrigade'
      ? true
      : config?.fireBrigades?.some((fb: any) => fb.fireBrigadeId === unitId);
    const isForester = unitTypeHint === 'foresterPatrol'
      ? true
      : config?.foresterPatrols?.some((fp: any) => fp.foresterPatrolId === unitId);
    
    // Skip if unitId doesn't match any known unit
    if (!isFireBrigade && !isForester) {
      console.warn(`[RecommendedDecisions] Unit ID ${unitId} not found in configuration. Skipping recommendation.`);
      return;
    }
    
    const unitType = isFireBrigade ? 'brigade' : 'forester';
    
    dispatch(
      sendBrigadeOrForesterMoveOrder(
        unitId, 
        sectorId, 
        unitType as "brigade" | "forester",
        'manual'
      ));
  }, [dispatch, mapConfiguration]);

  if (allRecommendations.length === 0) {
    return (
      <Box p={2}>
        <Typography variant="body1" color="text.secondary">
          No recommendations available at this time.
        </Typography>
      </Box>
    );
  }

  return (
    <Box p={2}>
      <Divider sx={{ mb: 2 }}>
        <Typography variant="h6" fontWeight="bold">
          Recommended Actions
        </Typography>
      </Divider>

      <List sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {allRecommendations
          .filter((action) => {
            const unitId = Number(action.unitId);
            const sectorId = Number(action.sectorId);
            return unitId > 0 && sectorId > 0;
          })
          .map((action, index) => {
            const unitId = Number(action.unitId);
            const sectorId = Number(action.sectorId);
            const unitTypeHint = action.unitType as ('fireBrigade' | 'foresterPatrol' | undefined);
            return (
              <ListItem
                key={`recommendation-${unitId}-${sectorId}-${index}`}
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  p: 1,
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                }}
              >
                <Typography variant="body1">
                  Send unit {unitId} to sector {sectorId}
                </Typography>
                <Button
                  variant="contained"
                  size="small"
                  color="success"
                  onClick={() => handleApplyRecommendation(unitId, sectorId, unitTypeHint)}
                >
                  Apply
                </Button>
              </ListItem>
            );
          })}
      </List>
    </Box>
  );
};

export default RecommendedDecisions;
