// maps
import { Map, useMap } from './MapLibre';
import { DeckGlOverlay } from './DeckGlOverlay';

// maps styles overrides
/**
 * This is a workaround to disable blue border around map component
 * when it is clicked
 */
import './maps-styles-overrides.css';

// material-ui
import { Grid, Box, Typography } from '@mui/material';
import { MainCard } from '../MainCard';
import { ReactNode, useCallback, useEffect, useState } from 'react';
import { Configuration } from '../../model/configuration';
import { useForestBorderLayer } from '../../features/maps/useForestBorderLayer';
import { useSectorsLayer } from '../../features/maps/useSectorsLayer';
import { useSelectedSectorLayer } from '../../features/maps/useSelectedSectorLayer';
import { useTargetSectorLayer } from '../../features/maps/useSelectedSectorLayer';
import { useOnSectorChange } from '../../features/maps/useOnSectorChange';
import { useOnTooltipChange } from '../../features/maps/useOnTooltipChange';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { setCurrentSectorId } from '../../store/mapConfigurationSlice';
// import { SensorMarkers } from './SensorMarkers';
import { CameraMarkers } from './CameraMarkers';
// import { ForesterPatrolMarkers } from './ForesterPatrolMarkers';
// import { FireBrigadeMarkers } from './FireBrigadeMarkers';
// import { FireBrigadeBaseMarkers } from './FireBrigadeBaseMarkers';
// import { ForesterPatrolBaseMarkers } from './ForesterPatrolBaseMarkers';
import { useForesterPatrolLayer } from '../../features/maps/useForesterPatrolLayer';
import { useFireBrigadeLayer } from '../../features/maps/useFireBrigadeLayer';

type Props = {
   targetSectorId: number|null;
   onClickHandler: (sectorId: number) => void;
}

const ForesterMapInner = (props: Props) => {
   const map = useMap('forester-map');
   const { configuration: mapConfiguration, currentSectorId } = useSelector(
      (state: RootState) => state.mapConfiguration,
   );
   const dispatch = useDispatch();

   const [tooltip, setTooltip] = useState<ReactNode>(null);

   // Disable panning in ForesterMap - only NewConfigurationMap should allow panning
   // But allow clicks and hovers for sector selection
   useEffect(() => {
      if (!map) return;
      
      // Disable panning but keep other interactions enabled
      map.dragPan?.disable();
      
      // Ensure zoom and other interactions still work
      map.scrollZoom?.enable();
      map.boxZoom?.enable();
      map.doubleClickZoom?.enable();
      map.touchZoomRotate?.enable();
      
      return () => {
         map.dragPan?.enable();
      };
   }, [map]);

   const [bounds, setBounds] = useState(Configuration.getBounds(mapConfiguration));
   useEffect(() => {
      setBounds(Configuration.getBounds(mapConfiguration));
   }, [mapConfiguration]); // TODO it should be useMemo
   useEffect(() => {
      if (!map) return;
      map.fitBounds(bounds);
   }, [bounds, map]);

   const forestBorderLayer = useForestBorderLayer(mapConfiguration);
   const sectorsLayer = useSectorsLayer(mapConfiguration, true, props.onClickHandler);
   const selectedSectorLayer = useSelectedSectorLayer(
      mapConfiguration.sectors.find(({ sectorId }) => sectorId === currentSectorId),
   );

   const targetSectorLayer = useTargetSectorLayer(
      mapConfiguration.sectors.find(({ sectorId }) => sectorId === props.targetSectorId && sectorId != currentSectorId) ,
   );
   const foresterPatrolLayer = useForesterPatrolLayer();
   const fireBrigadeLayer = useFireBrigadeLayer();

   const onSectorChange = useCallback(
      (sectorId: number | null) => {
         dispatch(setCurrentSectorId({ currentSectorId: sectorId }));
      },
      [dispatch],
   );
   useOnSectorChange(onSectorChange);

   if (Object.values(bounds).every((bound) => bound === 0))
      return (
         <Box
            sx={{
               display: 'flex',
               flexDirection: 'column',
               justifyContent: 'center',
               alignItems: 'center',
               backgroundColor: 'secondary.light',
               height: '800px',
            }}
         >
            <Typography variant="h2">No configuration selected!</Typography>
            <Typography variant="h4">Please select a configuration to see the map</Typography>
         </Box>
      );

   return (
      <>
         {tooltip}
         <DeckGlOverlay 
           overlayId="forester-map"
           capturePointerEvents={true}
           layers={[
             forestBorderLayer, 
             ...(Array.isArray(sectorsLayer) ? sectorsLayer : [sectorsLayer]),
             selectedSectorLayer, 
             targetSectorLayer,
             ...(Array.isArray(foresterPatrolLayer) ? foresterPatrolLayer : [foresterPatrolLayer]),
             ...(Array.isArray(fireBrigadeLayer) ? fireBrigadeLayer : [fireBrigadeLayer]),
           ].filter(Boolean)} />
         {/* Old render system wyłączony - używamy Deck.gl do renderowania agentów */}
         {/* <ForesterPatrolMarkers/> */}
         {/* <ForesterPatrolBaseMarkers/> */}
      </>
   );
};

export const ForesterMap = (props: Props) => {
   const { configuration: mapConfiguration } = useSelector(
      (state: RootState) => state.mapConfiguration,
   );
   const [bounds, setBounds] = useState(Configuration.getBounds(mapConfiguration));
   useEffect(() => {
      setBounds(Configuration.getBounds(mapConfiguration));
   }, [mapConfiguration]);

   if (Object.values(bounds).every((bound) => bound === 0))
      return (
         <Grid
            item
            xs={12}
            sx={{ mb: -2.25 }}
         >
            <MainCard
               hasContent={false}
               sx={{ mt: 1.5 }}
            >
               <Box
                  sx={{
                     display: 'flex',
                     flexDirection: 'column',
                     justifyContent: 'center',
                     alignItems: 'center',
                     backgroundColor: 'secondary.light',
                     height: '800px' /* TODO fix fixed height */,
                  }}
               >
                  <Typography variant="h2">No configuration selected!</Typography>
                  <Typography variant="h4">Please select a configuration to see the map</Typography>
               </Box>
            </MainCard>
         </Grid>
      );

   return (
      <Grid
         item
         xs={12}
         sx={{ mb: -2.25 }}
      >
         <MainCard
            hasContent={false}
            sx={{ mt: 1.5 }}
         >
            <Box sx={{ height: '800px' /* TODO fix fixed height */ }}>
               <Map
                  id="forester-map"
                  defaultBounds={bounds}
                  onDragstart={() => {
                     // Handled in ForesterMapInner
                  }}
               >
                  <ForesterMapInner {...props} />
               </Map>
            </Box>
         </MainCard>
      </Grid>
   );
};
