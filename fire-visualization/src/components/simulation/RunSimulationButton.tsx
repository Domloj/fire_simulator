import { Button } from '@mui/material';
import { useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '../../store/reduxStore';
import { isDefaultConfiguration } from '../../model/configuration';
import { useNavigate } from 'react-router-dom';
import { startFetchingConfigurationUpdate } from '../../store/serverCommunicationReducers';
import { openDrawer } from '../../store/menuSlice';

export const RunSimulationButton = () => {
  const { configuration: mapConfiguration } = useSelector((state: RootState) => state.mapConfiguration);
  const dispatch: AppDispatch = useDispatch();
  const navigate = useNavigate();  

  const fetchConfigurationUpdate = useCallback(() => {
    dispatch(startFetchingConfigurationUpdate());
    // Close drawer when simulation starts
    dispatch(openDrawer({ drawerOpen: false }));
  }, [dispatch]);

  const startSimulation = useCallback(() => {       
    navigate('/simulation');
    fetchConfigurationUpdate();
  }, [navigate, fetchConfigurationUpdate]);

  return (
    <Button
      variant="contained"
      onClick={startSimulation}
      sx={{ width: '150px' }}
      disabled={isDefaultConfiguration(mapConfiguration)}
    >
      Run simulation
    </Button>
  );
};
