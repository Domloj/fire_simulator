// material-ui
import { useTheme } from '@mui/material/styles';
import { AppBar, IconButton, Toolbar, useMediaQuery } from '@mui/material';
import { Box } from '@mui/material';

// assets
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';

import { StopSimulationButton } from '../../components/simulation/StopSimulationButton';
import AutoRecommendationSwitch from '../../components/simulation/AutoRecommendationSwitch';
import LlmModeSwitch from '../../components/simulation/LlmModeSwitch';
import DownloadConfigurationButton from '../../components/simulation/DownloadConfigurationButton';
import { SimulationPlaybackControls } from '../../components/simulation/SimulationPlaybackControls';

import { AppBarStyled } from '../AppBarStyled';

// ==============================|| MAIN LAYOUT - HEADER ||============================== //

export const Header = () => {
  const theme = useTheme();
  const matchDownMD = useMediaQuery(theme.breakpoints.down('lg'));

  // common header
  const mainHeader = (
    <Toolbar sx={{ justifyContent: 'end' }}>    
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          flexWrap: 'nowrap',
          '& > *': { minWidth: 190 },
        }}
      >
        <AutoRecommendationSwitch />
        <LlmModeSwitch />
        <SimulationPlaybackControls />
        <DownloadConfigurationButton />
        <StopSimulationButton />
      </Box>
    </Toolbar>
  );

  // app-bar params
  const appBar = {
    position: 'fixed',
    color: 'inherit',
    elevation: 0,
    sx: {
      borderBottom: `1px solid ${theme.palette.divider}`,
      boxShadow: theme.shadows[1],
    },
  } as const;

  return (
    <>
      {!matchDownMD ? (
        <AppBarStyled          
          {...appBar}
        >
          {mainHeader}
        </AppBarStyled>
      ) : (
        <AppBar {...appBar}>{mainHeader}</AppBar>
      )}
    </>
  );
};
