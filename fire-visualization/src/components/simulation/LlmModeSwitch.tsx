import { useState, useCallback } from 'react';
import { FormControlLabel, Switch } from '@mui/material';
import { useDispatch } from 'react-redux';
import { ThunkDispatch } from '@reduxjs/toolkit';
import { AnyAction } from 'redux';

import { simulationService } from '../../services/api/simulationService';
import { addLog } from '../../store/logsSlice';
import { RootState } from '../../store/reduxStore';

const LlmModeSwitch: React.FC = () => {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const dispatch: ThunkDispatch<RootState, unknown, AnyAction> = useDispatch();

  const handleToggle = useCallback(async () => {
    if (loading) return;

    const next = !enabled;
    setEnabled(next);
    setLoading(true);

    try {
      await simulationService.setLlmMode(next);

      dispatch(
        addLog({
          text: next
            ? '[LLM-Mode] Enabled LLM-driven recommendation mode (support uses LLM only, no MCTS)'
            : '[LLM-Mode] Disabled LLM-driven mode (support back to heuristic/default)',
          source: 'backend',
          level: 'info',
        })
      );
    } catch (e: any) {
      // Revert local toggle on error
      setEnabled(!next);
      dispatch(
        addLog({
          text: `[LLM-Mode] Failed to toggle LLM-driven mode: ${e?.message || 'unknown error'}`,
          source: 'backend',
          level: 'error',
        })
      );
      console.error('Failed to toggle LLM mode', e);
    } finally {
      setLoading(false);
    }
  }, [enabled, loading, dispatch]);

  return (
    <FormControlLabel
      control={
        <Switch
          checked={false}
          onChange={() => {}}
          disabled={true}
          color="secondary"
        />
      }
      label="LLM-driven recommendations (support as LLM)"
    />
  );
};

export default LlmModeSwitch;

