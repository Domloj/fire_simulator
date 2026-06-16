import { useTheme } from '@mui/material/styles';
import { AppBar, Box, Toolbar, useMediaQuery } from '@mui/material';
import { useLocation } from 'react-router-dom';
import { AppBarStyled } from './AppBarStyled';
import { RunSimulationButton } from '../components/simulation/RunSimulationButton';
import { StopSimulationButton } from '../components/simulation/StopSimulationButton';
import AutoRecommendationSwitch from '../components/simulation/AutoRecommendationSwitch';
import LlmModeSwitch from '../components/simulation/LlmModeSwitch';
import DownloadConfigurationButton from '../components/simulation/DownloadConfigurationButton';
import { SimulationPlaybackControls } from '../components/simulation/SimulationPlaybackControls';
import '../assets/styles/Navbar.css';

export const Navbar = () => {
  const theme = useTheme();
  const matchDownMD = useMediaQuery(theme.breakpoints.down('lg'));
  const location = useLocation();
  const isSimulationView = location.pathname.includes('/simulation');

  const homeHeader = (
    <Toolbar className="navbar-toolbar">
      <Box className="navbar-title">
        <Box className="navbar-title-text" sx={{ typography: 'h6', color: 'text.primary' }}>
          Fire Simulation System
        </Box>
      </Box>
      <Box className="navbar-actions">
        <RunSimulationButton />
      </Box>
    </Toolbar>
  );

  const simulationHeader = (
    <Toolbar className="navbar-toolbar">
      <Box className="navbar-title">
        <Box className="navbar-title-text" sx={{ typography: 'h6', color: 'text.primary' }}>
          Fire Simulation System
        </Box>
      </Box>
      <Box className="navbar-actions-simulation">
        <AutoRecommendationSwitch />
        <LlmModeSwitch />
        <SimulationPlaybackControls />
        <DownloadConfigurationButton />
        <StopSimulationButton />
      </Box>
    </Toolbar>
  );

  const appBar = {
    position: 'fixed' as const,
    color: 'inherit' as const,
    elevation: 0,
    sx: {
      borderBottom: `1px solid ${theme.palette.divider}`,
      boxShadow: theme.shadows[1],
      width: '100%',
      left: 0,
      right: 0,
      zIndex: theme.zIndex.drawer + 1,
    },
  };

  return (
    <>
      {!matchDownMD ? (
        <AppBarStyled {...appBar}>
          {isSimulationView ? simulationHeader : homeHeader}
        </AppBarStyled>
      ) : (
        <AppBar {...appBar}>
          {isSimulationView ? simulationHeader : homeHeader}
        </AppBar>
      )}
    </>
  );
};
