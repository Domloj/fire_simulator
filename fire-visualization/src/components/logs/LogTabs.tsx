import * as React from 'react';

import { useMemo, useState } from 'react';
import { Box, Tab, Tabs, FormControlLabel, Switch, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Divider } from '@mui/material';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../../store/reduxStore';
import { clearLogs, clearLlmLogs } from '../../store/logsSlice';
import { eventEmitter } from '@shared/utils/eventEmitter';

import LogTerminal from './LogTerminal';
import SimulationDetailsTable from '../../pages/SimulationDetailsTable';
import ActorsDetailsTable from '../../pages/ActorsDetailsTable';

import '../../assets/styles/LogTabs.css';

/**
 * So, this is the LogTabs component.
 * It provides a tabbed interface for viewing logs, mostliy MCTS recommendations from support services.
 * 
 * The component uses React hooks for state management and Redux for global state access.
 * @returns 
 */

export const LogTabs = () => {
  const dispatch: AppDispatch = useDispatch();
  const logs = useSelector((state: RootState) => state.logs.logs);
  const llmLogs = useSelector((state: RootState) => state.logs.llmLogs);
  const [tab, setTab] = useState(0);
  const [showAgentHistory, setShowAgentHistory] = useState(false);

  const statsTab = useMemo(
    () => (
      <Box className="log-tabs-stats" sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={showAgentHistory}
                onChange={(_, checked) => {
                  setShowAgentHistory(checked);
                  eventEmitter.emit('toggleAgentHistory', checked);
                }}
              />
            }
            label="History paths"
          />
        </Box>
        <Box sx={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
          <ActorsDetailsTable />
        </Box>
      </Box>
    ),
    [showAgentHistory],
  );

  const sectorsTab = useMemo(
    () => (
      <Box className="log-tabs-stats" sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Box sx={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
          <SimulationDetailsTable />
        </Box>
      </Box>
    ),
    [],
  );

  const helpTab = useMemo(
    () => (
      <Box sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
        <Box sx={{ 
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          overflowY: 'auto',
          p: 2,
          bgcolor: 'background.paper'
        }}>
          <Typography variant="h6" gutterBottom>
            Visualizer Legend
          </Typography>
          
          <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
            Sectors & Environment
          </Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Color/Element</TableCell>
                  <TableCell>Description</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  <TableCell><Box sx={{ width: 20, height: 20, bgcolor: 'rgb(200, 0, 0)', border: '1px solid #fff' }} /></TableCell>
                  <TableCell>Active Fire (Intensity based on opacity)</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 20, height: 20, bgcolor: 'rgb(30, 30, 30)', border: '1px solid #595959' }} /></TableCell>
                  <TableCell>Lost Sector (Burned out {'>'} 80%)</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 20, height: 20, bgcolor: 'rgba(255, 140, 0, 0.4)', border: '1px solid #fff' }} /></TableCell>
                  <TableCell>High Temperature / PM2.5 Warning</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 20, height: 20, border: '2px solid rgb(255, 60, 0)' }} /></TableCell>
                  <TableCell>Sector Border (Red outline)</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
            Agents (Fire Brigade)
          </Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
            <Table size="small">
              <TableBody>
                <TableRow>
                  <TableCell><Box sx={{ width: 16, height: 16, borderRadius: '50%', bgcolor: 'rgb(255, 0, 0)' }} /></TableCell>
                  <TableCell>Extinguishing</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 16, height: 16, borderRadius: '50%', bgcolor: 'rgb(0, 100, 255)' }} /></TableCell>
                  <TableCell>Travelling</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 16, height: 16, borderRadius: '50%', bgcolor: 'rgb(0, 200, 0)' }} /></TableCell>
                  <TableCell>Available</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
            Forester Patrols
          </Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
            <Table size="small">
              <TableBody>
                <TableRow>
                  <TableCell><Box sx={{ width: 16, height: 16, borderRadius: '50%', bgcolor: 'rgb(255, 165, 0)' }} /></TableCell>
                  <TableCell>Patrolling</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 16, height: 16, borderRadius: '50%', bgcolor: 'rgb(173, 216, 230)' }} /></TableCell>
                  <TableCell>Travelling</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 16, height: 16, borderRadius: '50%', bgcolor: 'rgb(128, 128, 128)' }} /></TableCell>
                  <TableCell>Available / Idle</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>

          <Typography variant="subtitle1" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
            Objects
          </Typography>
          <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
            <Table size="small">
              <TableBody>
                <TableRow>
                  <TableCell><Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: 'rgb(255, 235, 120)' }} /></TableCell>
                  <TableCell>Sensors (Yellow spectrum)</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell><Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: 'rgb(255, 0, 255)' }} /></TableCell>
                  <TableCell>Cameras (Magenta)</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>

          <Divider sx={{ my: 2 }} />
          
          <Typography variant="subtitle2" gutterBottom>
            Interactions:
          </Typography>
          <Typography variant="body2" component="div">
            <ul>
              <li>Click on a sector to see detailed state info.</li>
              <li>Hover over sectors to see quick stats.</li>
              <li>Use the zoom controls or mouse wheel to adjust view.</li>
              <li>Toggle History paths in STATS tab to see agent movement history.</li>
              <li>Labels and borders visibility scales automatically with zoom.</li>
            </ul>
          </Typography>
        </Box>
      </Box>
    ),
    [],
  );

  return (
    <Box className="log-tabs-container" sx={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(v)}
        textColor="primary"
        indicatorColor="primary"
        variant="fullWidth"
        className="log-tabs-tabs"
        sx={{ flexShrink: 0 }}
      >
        <Tab label="STATS" />
        <Tab label="SECTORS" />
        <Tab label="LOGS" />
        <Tab label="LLM" />
        <Tab label="HELP" />
      </Tabs>

      <Box className="log-tabs-content" sx={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {tab === 0 && statsTab}
        {tab === 1 && sectorsTab}
        {tab === 2 && (
          <Box sx={{ flex: 1, width: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', position: 'relative' }}>
            <LogTerminal
              title="Simulation Logs"
              entries={logs}
              onClear={() => dispatch(clearLogs())}
            />
          </Box>
        )}
        {tab === 3 && (
          <Box sx={{ flex: 1, width: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden', position: 'relative' }}>
            <LogTerminal
              title="Strategic Intelligence Logs"
              entries={llmLogs}
              onClear={() => dispatch(clearLlmLogs())}
            />
          </Box>
        )}
        {tab === 4 && helpTab}
      </Box>
    </Box>
  );
};

export default LogTabs;
