import { useMemo } from 'react';
import { ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { useSelector, shallowEqual } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { eventEmitter } from '@shared/utils/eventEmitter';

// Optimized, low-frequency layer for fire brigades (used when not using a dedicated fast-updates renderer)
export const useFireBrigadeLayer = () => {
  // An array of strings used to trigger updates only when important brigade props change
  // const fireBrigadeMeta = useSelector(
  //   (state: RootState) => (state.mapConfiguration.configuration?.fireBrigades || []).map(fb => `${fb.fireBrigadeId}:${fb.state}:${fb.sectorId ?? 0}`),
  //   shallowEqual
  // );

  // const fireBrigades = useSelector((state: RootState) => state.mapConfiguration.configuration?.fireBrigades || []);
  // const sectorCount = useSelector((state: RootState) => state.mapConfiguration.configuration?.sectors?.length || 0, shallowEqual);

  // const data = useMemo(() => {
  //   if (!fireBrigades || fireBrigades.length === 0) return [];

  //   return fireBrigades
  //     .map((fb) => {
  //       const loc = fb.currentLocation;
  //       if (!loc || typeof loc.longitude !== 'number' || typeof loc.latitude !== 'number') return null;
  //       return {
  //         fireBrigadeId: fb.fireBrigadeId,
  //         longitude: loc.longitude,
  //         latitude: loc.latitude,
  //         state: fb.state,
  //       };
  //     })
  //     .filter(Boolean) as Array<{ fireBrigadeId: number; longitude: number; latitude: number; state: string }>;
  // }, [fireBrigades]);

  // const radius = useMemo(() => (sectorCount > 400 ? 2.5 : sectorCount > 100 ? 3.5 : sectorCount > 25 ? 4.5 : 5), [sectorCount]);
  // const radiusMin = useMemo(() => (sectorCount > 400 ? 2 : sectorCount > 100 ? 3 : sectorCount > 25 ? 4 : 4), [sectorCount]);
  // const radiusMax = useMemo(() => (sectorCount > 400 ? 4 : sectorCount > 100 ? 6 : sectorCount > 25 ? 7 : 8), [sectorCount]);

  // const getStateColor = (state: string): [number, number, number] => {
  //   switch (state) {
  //     case 'TRAVELLING':
  //       return [0, 100, 255];
  //     case 'EXTINGUISHING':
  //       return [255, 0, 0];
  //     case 'AVAILABLE':
  //       return [0, 200, 0];
  //     default:
  //       return [128, 128, 128];
  //   }
  // };

  // const layers = useMemo(() => {
  //   if (!data || data.length === 0) {
  //     console.debug('[useFireBrigadeLayer] creating empty fire-brigade-layer (no data)');
  //     // return a harmless empty layer so deck has a stable layer array
  //     return [new ScatterplotLayer({ id: 'fire-brigade-layer', data: [] })];
  //   }

  //   const scatterplotLayer = new ScatterplotLayer({
  //     id: 'fire-brigade-layer',
  //     data,
  //     getPosition: (d: any) => [d.longitude, d.latitude],
  //     getFillColor: (d: any) => getStateColor(d.state),
  //     getRadius: () => radius,
  //     radiusUnits: 'pixels',
  //     radiusMinPixels: radiusMin,
  //     radiusMaxPixels: radiusMax,
  //     pickable: true,
  //     onClick: (info: any) => {
  //       if (info.object) eventEmitter.emit('fire-brigade-click', info.object);
  //     },
  //     updateTriggers: {
  //       // only re-evaluate positions/colors when the meta array changes
  //       getPosition: fireBrigadeMeta,
  //       getFillColor: fireBrigadeMeta,
  //     },
  //   });

  //   const textLayer = new TextLayer({
  //     id: 'fire-brigade-text-layer',
  //     data: data.map((d) => ({ 
  //       position: [d.longitude, d.latitude] as [number, number], 
  //       text: `FireBrigade_${d.fireBrigadeId.toString().padStart(2, '0')}`,
  //     })),
  //     getPosition: (d: any) => d.position,
  //     getText: (d: any) => d.text,
  //     getSize: sectorCount > 100 ? 6 : sectorCount > 50 ? 7 : sectorCount > 25 ? 8 : 8,
  //     getColor: [255, 255, 255, 255], // white text
  //     getTextAnchor: 'middle',
  //     getAlignmentBaseline: 'center',
  //     getPixelOffset: [0, -12],
  //     background: true,
  //     getBackgroundColor: [0, 0, 0, 240], // black background with slight transparency
  //     fontFamily: 'Monaco, monospace',
  //     fontWeight: 'bold',
  //     billboard: true,
  //     pickable: true,
  //     updateTriggers: {
  //       getPosition: fireBrigadeMeta,
  //       getText: fireBrigadeMeta,
  //     },
  //   });

  //   return [scatterplotLayer, textLayer];
  // }, [data, fireBrigadeMeta, radius, radiusMin, radiusMax, sectorCount]);

  // return layers;
};
