// material-ui
import { Box, Grid, CircularProgress, Typography } from '@mui/material';
import { useEffect, lazy, Suspense } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { ConfigurationForm } from '@features/configuration/ConfigurationForm';
import { AppDispatch, RootState } from '../store/reduxStore';
import { resumeSimulationIfRunning } from '../store/serverCommunicationReducers';

// OPTIMIZATION: Lazy load map components - reduces initial bundle size
const MapWrapper = lazy(() => import('@features/maps').then(module => ({ default: module.MapWrapper })));
const MainMap = lazy(() => import('../components/maps/MainMap').then(module => ({ default: module.MainMap })));

// Loading fallback component
const MapLoadingFallback = () => (
  <Box 
    sx={{ 
      display: 'flex', 
      flexDirection: 'column',
      alignItems: 'center', 
      justifyContent: 'center', 
      height: '100%',
      gap: 2,
    }}
  >
    <CircularProgress size={60} />
    <Typography variant="h6" color="text.secondary">
      Loading map...
    </Typography>
  </Box>
);

export const MainPage = () => {
  const dispatch = useDispatch<AppDispatch>();
  const currentSectorId = useSelector((state: RootState) => state.mapConfiguration.currentSectorId);
  const isSimulationRunning = useSelector((state: RootState) => state.serverCommunication.isFetching);
  const hasSelectedSector = currentSectorId !== null && !isSimulationRunning;

  useEffect(() => {
    dispatch(resumeSimulationIfRunning());
  }, [dispatch]);

  return (
    <Box sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', margin: 0, padding: 0 }}>
      <Grid
        container
        spacing={0}
        sx={{
          flex: 1,
          minHeight: 0,
          height: '100%',
          margin: 0,
          padding: 0,
          '& > .MuiGrid-item': {
            pl: 0,
            pt: 0,
          },
        }}
      >
        {/* Map - full width when no sector selected, 8/12 when sector selected */}
        <Grid 
          item 
          xs={12} 
          md={hasSelectedSector ? 8 : 12} 
          sx={{ 
            display: 'flex', 
            flexDirection: 'column', 
            minHeight: 0,
            height: '100%',
            pt: 0,
          }}
        >
          <Box sx={{ flex: 1, width: '100%', height: '100%', position: 'relative', minHeight: 0 }}>
            <Suspense fallback={<MapLoadingFallback />}>
              <MapWrapper>
                <MainMap />
              </MapWrapper>
            </Suspense>
          </Box>
        </Grid>

        {/* Right: Sector Edit Pane (ConfigurationForm) - only visible when sector is selected */}
        {hasSelectedSector && (
          <Grid item xs={12} md={4} sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%' }}>
            <Box
              sx={{
                flex: 1,
                minHeight: 0,
                overflow: 'auto',
                paddingTop: '64px',
                borderRadius: 0,
                height: '100%',
                boxSizing: 'border-box',
              }}
            >
              <ConfigurationForm />
            </Box>
          </Grid>
        )}
      </Grid>
    </Box>
  );
};
