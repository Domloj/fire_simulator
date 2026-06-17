import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { MainDrawer } from './Drawer/MainDrawer';
import { Navbar } from './Navbar';
import { useDrawerState } from './hooks/useDrawerState';
import '../assets/styles/AppLayout.css';

export const AppLayout = () => {
  const theme = useTheme();
  const { open, handleDrawerToggle } = useDrawerState();
  const mainPaneClasses = `app-main-pane ${open ? 'app-main-pane-drawer-open' : 'app-main-pane-drawer-closed'}`;

  return (
    <Box className="app-layout-container">
      <Navbar />
      <Box className="app-layout-content">
        <MainDrawer open={open} handleDrawerToggle={handleDrawerToggle} />
        <Box
          component="main"
          className={mainPaneClasses}
          sx={{
            borderTop: `1px solid ${theme.palette.divider}`,
            transition: theme.transitions.create(['width', 'margin-left'], {
              easing: theme.transitions.easing.sharp,
              duration: theme.transitions.duration.leavingScreen,
            }),
          }}
        >
          <Box className="app-main-pane-content">
            <Outlet />
          </Box>
        </Box>
      </Box>
    </Box>
  );
};
