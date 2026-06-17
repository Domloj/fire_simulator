// import { createElement, CSSProperties, useMemo, useRef } from 'react';
// import { Configuration } from '../../model/configuration';
// import { PolygonLayer } from '@deck.gl/layers';
// import { Sector } from '../../model/sector';
// import { PickingInfo } from '@deck.gl/core';
// import { eventEmitter } from '@shared/utils/eventEmitter';
// import { Box, List, ListItem, ListItemText } from '@mui/material';

// const styles = {
//   tooltip: {
//     display: 'block',
//     zIndex: 1,
//     position: 'absolute',
//     backgroundColor: 'rgba(66, 66, 66, 0.6)',
//     color: 'white',
//     padding: '5px',
//     borderRadius: '5px',
//   } as const,
// } satisfies Record<string, CSSProperties>;

// let _lastHover = { sectorId: null as number | null, ts: 0 };
// const HOVER_THROTTLE_MS = 0;
// let _sectorLayerRecreateCount = 0;
// let _lastRecreateTime = Date.now();

// export const useSectorsLayer = ({ sectors }: Configuration, disableOnHover?: boolean, onClickHandler?: (sectorId: number) => void) => {

//   return useMemo(() => {
//     _sectorLayerRecreateCount++;
//     const now = Date.now();
//     const timeSinceLastRecreate = now - _lastRecreateTime;
//     console.log(`[useSectorsLayer] Layer recreated #${_sectorLayerRecreateCount} | Time since last: ${timeSinceLastRecreate}ms | Sectors count: ${sectors?.length || 0}`);
//     _lastRecreateTime = now;
    
//     return new PolygonLayer<Sector>({
//         id: 'PolygonLayer',
//         data: sectors,        

//         extruded: false,
//         filled: true,
//         stroked: true,
//         getPolygon: (sector) => sector.contours,
//         getFillColor: (sector)=> {
//           let fireLevel;
//           if(sector.initialState.temperature <= 35){
//             fireLevel = 1;
//           }
//           else if(sector.initialState.temperature <= 45){
//             fireLevel = 2;
//           }
//           else if(sector.initialState.temperature <= 55){
//             fireLevel = 3;          
//           }          
//           else {
//             fireLevel = 4;          
//           }

//           let pm2_5Level;

//           if(sector.initialState.pm2_5Concentration <= 50){
//             pm2_5Level = 1;
//           }
//           else if(sector.initialState.pm2_5Concentration <= 100){
//             pm2_5Level = 2;
//           }
//           else if(sector.initialState.pm2_5Concentration <= 250){
//             pm2_5Level = 3;          
//           }          
//           else {
//             pm2_5Level = 4;          
//           }

//           if(Math.max(fireLevel, pm2_5Level) === 1){
//             return [0, 0, 0, 0]
//           }   
//           else if(Math.max(fireLevel, pm2_5Level) === 2){
//             return [255, 200, 0, 100]
//           }
//           else if(Math.max(fireLevel, pm2_5Level) === 3){
//             return [255, 140, 0, 100]
//           }
//           else if(Math.max(fireLevel, pm2_5Level) === 4){
//             return [200, 0, 0, 100]
//           }
          
//           return [0, 0, 0, 0];
                 
//         },
//         // Use a bolder, more vivid red outline between sectors so borders feel "wilder"
//         getLineColor: [255, 60, 0],
//         // Increase line width for a stronger visual presence on grid maps (e.g., 4x4 sectors)
//         getLineWidth: () => (sectors && sectors.length === 1 ? 1 : 8),
//         lineWidthMinPixels: 2,
//         // Stronger highlight color for hover
//         highlightColor: [255, 80, 0, 220],
//         autoHighlight: true,
//         pickable: true,
//         onHover: (pickingInfo: PickingInfo<Sector>) => {
//           if (disableOnHover) return
//           const now = Date.now();
//           const sectorId = pickingInfo?.object?.sectorId ?? null;

//           // Throttle frequent hover updates to avoid DOM thrash and potential WebGL redraws
//           if (sectorId === _lastHover.sectorId && now - _lastHover.ts < HOVER_THROTTLE_MS) return;
//           _lastHover = { sectorId, ts: now };

//           const { x, y, object: sector, viewport } = pickingInfo;
//           if (!sector) {
//             eventEmitter.emit('onTooltipChange', null);
//             return;
//           }

//           // check the currently shown tooltip
//           // if the sector is the same do not update the tooltip
//           const oldTooltip = document.getElementById('tooltip-sector');
//           if (oldTooltip && oldTooltip.className === `sector-${sector.sectorId}`) return;

//           const sectorCenterCoords = {
//             longitude:
//               sector.contours.reduce((avgLng: number, point: [number, number]) => avgLng + point[0], 0) /
//               sector.contours.length,
//             latitude:
//               sector.contours.reduce((avgLat: number, point: [number, number]) => avgLat + point[1], 0) /
//               sector.contours.length,
//           };
//           const sectorCenterPixels = viewport?.project([sectorCenterCoords.longitude, sectorCenterCoords.latitude]);

//           const tooltip = createElement(
//             Box,
//             {
//               id: `tooltip-sector`,
//               className: `sector-${sector.sectorId}`,
//               sx: {
//                 ...styles.tooltip,
//                 left: Math.round(sectorCenterPixels?.[0] ?? x) + 'px',
//                 top: Math.round(sectorCenterPixels?.[1] ?? y) + 'px',
//               },
//             },
//             createElement(
//               List,
//               { dense: false },
//               Configuration.sectors
//                 .toString(sector)
//                 .split('\n')
//                 .map((str, i) => {
//                   return createElement(ListItem, { sx: { py: 0 }, key: i }, createElement(ListItemText, { primary: str }));
//                 }),
//             ),
//           );
//           eventEmitter.emit('onTooltipChange', tooltip);
//         },
//         onClick: (pickingInfo: PickingInfo<Sector>) => {
//           const { object: sector } = pickingInfo;
          
//           if (onClickHandler && sector) {
//             try {
//               onClickHandler(sector.sectorId);
//             } catch (error) {
//               window.__LAST_SECTOR_ERROR__ = error;
//             }
//           }
          
//           if (disableOnHover) {
//             return;
//           }
          
//           const sectorId = sector?.sectorId ?? null;
//           try {
//             eventEmitter.emit('onSectorChange', sectorId);
//           } catch (error) {
//             window.__LAST_SECTOR_ERROR__ = error;
//           }
//         },
//         autoHighlight: true,
//         highlightColor: [116, 146, 195, 128],
//       });
//     },
//     [sectors],
//   );
// };
