import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';
import { MainDrawer } from './Drawer/MainDrawer';
import { Navbar } from './Navbar';
import { MainPane } from './components/MainPane';
import { useDrawerState } from './hooks/useDrawerState';
import '../assets/styles/MainLayout.css';

export const MainLayout = () => {
  const { open, handleDrawerToggle } = useDrawerState();

  return (
    <Box className="main-layout-container">
      <Navbar />
      <MainDrawer open={open} handleDrawerToggle={handleDrawerToggle} />
      <MainPane open={open}>
        <Outlet />
      </MainPane>
    </Box>
  );
};
