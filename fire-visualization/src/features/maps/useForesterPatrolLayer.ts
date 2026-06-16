import { useMemo } from 'react';
import { ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { useSelector, shallowEqual } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { ForesterPatrol } from '../../model/ForesterPatrol';
import { performanceMonitor } from '@shared/utils/performanceMonitor';

export const useForesterPatrolLayer = () => {
  // const foresterPatrolMeta = useSelector((state: RootState) => (state.mapConfiguration.configuration?.foresterPatrols || []).map(fp => `${fp.foresterPatrolId}:${fp.state}:${fp.sectorId ?? 0}`), shallowEqual);
  // const foresterPatrols    = useSelector((state: RootState) => state.mapConfiguration.configuration?.foresterPatrols || [], shallowEqual);
  // const sectorCount        = useSelector((state: RootState) => state.mapConfiguration.configuration?.sectors?.length || 0, shallowEqual);

  // const layerData = useMemo(() => {
  //   if (!foresterPatrols || foresterPatrols.length === 0) {
  //     return [];
  //   }

  //   const data = foresterPatrols.map((fp) => {
  //     const loc = fp.currentLocation;
  //     return {
  //       id: fp.foresterPatrolId,
  //       position: loc && typeof loc.longitude === 'number' && typeof loc.latitude === 'number'
  //         ? [loc.longitude, loc.latitude] as [number, number]
  //         : null,
  //       state: fp.state,
  //       foresterPatrolId: fp.foresterPatrolId,
  //     };
  //   }).filter(d => d.position !== null) as any[];

  //   if (data.length < foresterPatrols.length) {
  //     const missing = foresterPatrols.length - data.length;
  //     console.warn(`[useForesterPatrolLayer] ${missing} patrols have no valid location`);
  //   }
  //   return data;
  // }, [foresterPatrols]);

  // const textLayerData = useMemo(() => {
  //   if (!foresterPatrols || foresterPatrols.length === 0) {
  //     return [];
  //   }
  //   return foresterPatrols.map((fp) => {
  //     const loc = fp.currentLocation;
  //     if (!loc || typeof loc.longitude !== 'number' || typeof loc.latitude !== 'number') return null;
  //     return {
  //       position: [loc.longitude, loc.latitude] as [number, number],
  //       text: `ForesterPatrol_${fp.foresterPatrolId.toString().padStart(2, '0')}`,
  //       id: fp.foresterPatrolId,
  //     };
  //   }).filter(Boolean) as any[];
  // }, [foresterPatrols]);

  // const markerRadius    = useMemo(() => sectorCount > 400 ? 4 : sectorCount > 100 ? 6 : sectorCount > 25 ? 7 : 8, [sectorCount]);
  // const markerRadiusMin = useMemo(() => sectorCount > 400 ? 3 : sectorCount > 100 ? 4 : sectorCount > 25 ? 5 : 6, [sectorCount]);
  // const markerRadiusMax = useMemo(() => sectorCount > 400 ? 7 : sectorCount > 100 ? 10 : sectorCount > 25 ? 12 : 14, [sectorCount]);

  // const getStateColor = (state: string): [number, number, number] => {
  //   switch (state) {
  //     case 'TRAVELLING':
  //       return [0, 100, 255];  // Blue
  //     case 'PATROLLING':
  //       return [0, 200, 0];    // Green
  //     case 'AVAILABLE':
  //       return [0, 200, 0];    // Green
  //     default:
  //       return [128, 128, 128]; // Gray
  //   }
  // };

  // const layers = useMemo(() => {
  //   if (!layerData || layerData.length === 0) {
  //     console.debug('[useForesterPatrolLayer] no patrol layer data (0 items)');
  //     return [];
  //   }

  //   console.debug('[useForesterPatrolLayer] creating layers', { count: layerData.length, ids: ['forester-patrol-markers', 'forester-patrol-labels'] });
  //   return [
  //     new ScatterplotLayer({
  //       id: 'forester-patrol-markers',
  //       data: layerData,
  //       getPosition: (d: any) => d.position || [0, 0],
  //       getRadius: () => markerRadius,
  //       radiusMinPixels: markerRadiusMin,
  //       radiusMaxPixels: markerRadiusMax,
  //       getColor: (d: any) => getStateColor(d.state),
  //       pickable: true,
  //       autoHighlight: true,
  //       updateTriggers: {
  //         getPosition: layerData,
  //         getColor: layerData,
  //       },
  //     }),
  //     new TextLayer({
  //       id: 'forester-patrol-labels',
  //       data: layerData.map((d) => ({
  //         position: d.position as [number, number],
  //         text: `ForesterPatrol_${d.foresterPatrolId.toString().padStart(2, '0')}`,
  //       })),
  //       getPosition: (d: any) => d.position,
  //       getText: (d: any) => d.text,
  //       getSize: () => 12,
  //       getAngle: 0,
  //       getColor: [255, 255, 255, 255], // white text
  //       getTextAnchor: () => 'middle' as const,
  //       getAlignmentBaseline: () => 'center' as const,
  //       background: true,
  //       getBackgroundColor: [0, 0, 0, 240],
  //       fontFamily: 'Monaco, monospace',
  //       fontWeight: 'bold',
  //       billboard: true,
  //       pickable: true,
  //       updateTriggers: { getPosition: textLayerData, },
  //     }),
  //   ];
  // }, [layerData, textLayerData, markerRadius, markerRadiusMin, markerRadiusMax]);

  // return layers;
};
