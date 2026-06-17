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
import { useFireBrigadeLayer } from '../../features/maps/useFireBrigadeLayer';

type Props = {
   targetSectorId: number|null;
   onClickHandler: (sectorId: number) => void;
}

const FireBrigadeMapInner = (props: Props) => {
   const map = useMap('fire-brigade-map');
   const { configuration: mapConfiguration, currentSectorId } = useSelector(
      (state: RootState) => state.mapConfiguration,
   );

   const dispatch = useDispatch();
   const [tooltip, setTooltip] = useState<ReactNode>(null);

   useEffect(() => {
      if (!map) return;
      
      map.dragPan?.disable();
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
      const newBounds = Configuration.getBounds(mapConfiguration);
      if (JSON.stringify(newBounds) !== JSON.stringify(bounds)) {
         setBounds(newBounds);
      }
   }, [mapConfiguration, bounds]); 

   useEffect(() => {
      if (!map) return;
      if (props.targetSectorId == null) return;
      const sector = mapConfiguration.sectors.find(s => s.sectorId === props.targetSectorId);
      if (!sector || !sector.contours || sector.contours.length === 0) return;

      const sw = [Math.min(...sector.contours.map(c => c[0])), Math.min(...sector.contours.map(c => c[1]))] as [number, number];
      const ne = [Math.max(...sector.contours.map(c => c[0])), Math.max(...sector.contours.map(c => c[1]))] as [number, number];
      try {
         map.fitBounds([sw, ne], { padding: 80 });
      } catch (e) {
         // pass
      }
   }, [map, props.targetSectorId, mapConfiguration.sectors]);

   const forestBorderLayer = useForestBorderLayer(mapConfiguration);
   const sectorsLayer = useSectorsLayer(mapConfiguration, true, props.onClickHandler);
   const selectedSectorLayer = useSelectedSectorLayer(
      mapConfiguration.sectors.find(({ sectorId }) => sectorId === currentSectorId),
   );
 
   const targetSectorLayer = useTargetSectorLayer(
      mapConfiguration.sectors.find(({ sectorId }) => sectorId === props.targetSectorId && sectorId != currentSectorId) ,
   );
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
           overlayId="fire-brigade-map"
           capturePointerEvents={true}
           layers={[
             forestBorderLayer, 
             ...(Array.isArray(sectorsLayer) ? sectorsLayer : [sectorsLayer]),
             selectedSectorLayer, 
             targetSectorLayer,
             ...(Array.isArray(fireBrigadeLayer) ? fireBrigadeLayer : [fireBrigadeLayer]),
           ].filter(Boolean)} />
         {/* Old render system - updated with fast updates */}
         {/* <FireBrigadeMarkers /> */}
         {/* <FireBrigadeBaseMarkers /> */}
      </>
   );
};

export const FireBrigadeMap = (props: Props) => {
   const { configuration: mapConfiguration } = useSelector(
      (state: RootState) => state.mapConfiguration,
   );
   const [bounds, setBounds] = useState(Configuration.getBounds(mapConfiguration));
   useEffect(() => {
      const newBounds = Configuration.getBounds(mapConfiguration);
      if (JSON.stringify(newBounds) !== JSON.stringify(bounds)) {
         setBounds(newBounds);
      }
   }, [mapConfiguration, bounds]);

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
                  id="fire-brigade-map"
                  defaultBounds={bounds}
                  onDragstart={() => {
                     // Handled in FireBrigadeMapInner
                  }}
               >
                  <FireBrigadeMapInner {...props} />
               </Map>
            </Box>
         </MainCard>
      </Grid>
   );
};
