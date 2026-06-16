import { useMemo } from 'react';
import { ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { Camera } from '../../model/camera';

export const useCameraLayer = () => {
  const cameras = useSelector((state: RootState) => state.mapConfiguration.configuration?.cameras || []);
  // Get sector count to scale label visibility
  const sectorCount = useSelector((state: RootState) => state.mapConfiguration.configuration?.sectors?.length || 0);

  const layers = useMemo(() => {
    if (!cameras || cameras.length === 0) {
      return [new ScatterplotLayer({ id: 'camera-layer', data: [] })];
    }

    const scatterplotLayer = new ScatterplotLayer({
      id: 'camera-layer',
      data: cameras.map((c) => ({
        cameraId: c.cameraId,
        longitude: c.location.longitude,
        latitude: c.location.latitude
      })),
      getPosition: (d: any) => [d.longitude, d.latitude],
      getFillColor: [255, 0, 255], // Magenta
      getRadius: sectorCount > 400 ? 2.5 : sectorCount > 100 ? 3.5 : sectorCount > 25 ? 4.5 : 5,
      radiusUnits: 'pixels',
      radiusMinPixels: sectorCount > 400 ? 2 : sectorCount > 100 ? 3 : sectorCount > 25 ? 4 : 4,
      radiusMaxPixels: sectorCount > 400 ? 4 : sectorCount > 100 ? 6 : sectorCount > 25 ? 7 : 8,
      pickable: true,
    });

    const textLayer = new TextLayer({
      id: 'camera-text-layer',
      data: cameras.map((c) => ({
        position: [c.location.longitude, c.location.latitude] as [number, number],
        text: `Camera_${c.cameraId.toString().padStart(2, '0')}`,
      })),
      getPosition: (d: any) => d.position,
      getText: (d: any) => d.text,
      getSize: sectorCount > 100 ? 6 : sectorCount > 50 ? 7 : sectorCount > 25 ? 8 : 8,
      getColor: [255, 255, 255, 255],
      getAngle: 0,
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'bottom',
      getPixelOffset: [0, -15],
      background: true,
      getBackgroundColor: [0, 0, 0, 240],
      fontFamily: 'Monaco, monospace',
      fontWeight: 'bold',
      billboard: true,
    });

    return [scatterplotLayer, textLayer];
  }, [cameras, sectorCount]);

  return layers;
};
