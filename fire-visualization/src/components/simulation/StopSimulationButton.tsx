import { Button } from '@mui/material';
import { useCallback } from 'react';
import { useDispatch } from 'react-redux';
import { AppDispatch } from '../../store/reduxStore';
import { useNavigate } from 'react-router-dom';
import { abortConnection, sendStopRequest } from '../../store/serverCommunicationReducers';

export const StopSimulationButton = () => {
  const dispatch: AppDispatch = useDispatch();
  const navigate = useNavigate();  

  const stopSimulation = useCallback(() => {
    dispatch(sendStopRequest());
    navigate('/');
    dispatch(abortConnection());
  }, [dispatch, navigate]);

  return (
    <Button
      variant="contained"
      color='error'
      onClick={stopSimulation}
      sx={{ width: '150px' }}      
    >
      Stop simulation
    </Button>
  );
};
