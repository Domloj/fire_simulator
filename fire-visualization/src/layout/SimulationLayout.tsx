import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { useTheme } from '@mui/material/styles';
import { Box, Toolbar, useMediaQuery } from '@mui/material';
import { MainDrawer } from './Drawer/MainDrawer';
import { Header } from './SimulationLayout/Header';
import { RootState } from '../store/reduxStore';
import { openDrawer } from '../store/menuSlice';


export const SimulationLayout = () => {
  const theme = useTheme();

  return (
    <Box sx={{ display: 'flex', width: '100%' }}>
      <Header/>      
      <Box
        component="main"
        sx={{ width: '100%', flexGrow: 1, p: { xs: 2, sm: 3 } }}
      >
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
};
