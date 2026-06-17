import { useCallback, useState } from 'react';
import { Box, IconButton, Tooltip } from '@mui/material';
import {
  PauseOutlined,
  CaretRightOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons';
import { simulationService } from '../../services/api/simulationService';

// Sterowanie przebiegiem symulacji: pauza/wznowienie oraz ręczny krok w przód
// i wstecz. Kroki ręczne mają sens tylko w pauzie, więc poza nią są wyłączone.
export const SimulationPlaybackControls = () => {
  const [paused, setPaused] = useState(false);
  const [busy, setBusy] = useState(false);

  const togglePause = useCallback(async () => {
    setBusy(true);
    try {
      if (paused) {
        await simulationService.resumeSimulation();
        setPaused(false);
      } else {
        await simulationService.pauseSimulation();
        setPaused(true);
      }
    } catch {
      // pomijamy, stan przycisku zostaje bez zmian
    } finally {
      setBusy(false);
    }
  }, [paused]);

  const stepForward = useCallback(async () => {
    setBusy(true);
    try {
      await simulationService.stepForward(1);
    } catch {
      // pomijamy
    } finally {
      setBusy(false);
    }
  }, []);

  const stepBack = useCallback(async () => {
    setBusy(true);
    try {
      await simulationService.stepBack(1);
    } catch {
      // pomijamy
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'center' }}>
      <Tooltip title="Krok wstecz">
        <span>
          <IconButton size="small" onClick={stepBack} disabled={!paused || busy}>
            <StepBackwardOutlined />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title={paused ? 'Wznów' : 'Pauza'}>
        <IconButton size="small" color="primary" onClick={togglePause} disabled={busy}>
          {paused ? <CaretRightOutlined /> : <PauseOutlined />}
        </IconButton>
      </Tooltip>
      <Tooltip title="Krok w przód">
        <span>
          <IconButton size="small" onClick={stepForward} disabled={!paused || busy}>
            <StepForwardOutlined />
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );
};

export default SimulationPlaybackControls;
