// material-ui
import { Box, Grid, CircularProgress, Typography } from '@mui/material';
import { lazy, Suspense } from 'react';
import LogTabs from '../components/logs/LogTabs';

// OPTIMIZATION: Lazy load map components - reduces initial bundle size by ~15-20MB
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

export const SimulationPage = () => {
  return (
    <Box 
      className="simulation-page-container"
      sx={{ 
        display: 'flex', 
        flexDirection: 'column', 
        height: '100%', 
        width: '100%', 
        padding: 0, 
        overflow: 'hidden',
        margin: 0,
      }}
    >
      <Grid
        container
        spacing={0}
        sx={{
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          '& > .MuiGrid-item': {
            pl: 0,
            pt: 0,
          },
        }}
      >
        {/* Left: Map */}
        <Grid item xs={12} md={8} sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden'}}>
          <Box sx={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <Suspense fallback={<MapLoadingFallback />}>
              <MapWrapper>
                <MainMap />
              </MapWrapper>
            </Suspense>
          </Box>
        </Grid>

        {/* Right: LogTabs only (STATS | LOGS | LLM) */}
        <Grid item xs={12} md={4} sx={{ display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
          <Box
            sx={{
              flex: 1,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              paddingTop: '64px',
              paddingX: '8px',
              paddingBottom: '8px',
              height: 'calc(100vh - 48px)',
              boxSizing: 'border-box',
              overflow: 'hidden',
            }}
          >
            <LogTabs />
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
};
