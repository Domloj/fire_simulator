import { useMemo } from 'react';
import { ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { SensorType } from '../../model/sensor';

export const useSensorLayer = () => {
  const sensors = useSelector((state: RootState) => state.mapConfiguration.configuration?.sensors || []);
  // Get sector count to scale label visibility
  const sectorCount = useSelector((state: RootState) => state.mapConfiguration.configuration?.sectors?.length || 0);

  const layers = useMemo(() => {
    if (!sensors || sensors.length === 0) {
      return [new ScatterplotLayer({ id: 'sensor-layer', data: [] })];
    }

    // Color mapping based on sensor type - spectrum of yellow
    const getSensorTypeColor = (sensorType: string): [number, number, number] => {
      switch (sensorType) {
        case 'TEMPERATURE_AND_AIR_HUMIDITY':
          return [255, 255, 150]; // Light yellow
        case 'WIND_SPEED':
          return [255, 235, 120]; // Pale yellow
        case 'WIND_DIRECTION':
          return [255, 220, 100]; // Soft yellow
        case 'LITTER_MOISTURE':
          return [255, 200, 80]; // Golden yellow
        case 'PM2_5':
          return [255, 180, 60]; // Amber yellow
        case 'CO2':
          return [255, 160, 40]; // Dark yellow/orange
        default:
          return [255, 240, 180]; // Very light yellow
      }
    };

    // Short name for sensor type
    const getSensorTypeShortName = (sensorType: string): string => {
      switch (sensorType) {
        case 'TEMPERATURE_AND_AIR_HUMIDITY':
          return 'TEMP';
        case 'WIND_SPEED':
          return 'WIND_SP';
        case 'WIND_DIRECTION':
          return 'WIND_DIR';
        case 'LITTER_MOISTURE':
          return 'MOIST';
        case 'PM2_5':
          return 'PM2_5';
        case 'CO2':
          return 'CO2';
        default:
          return 'SENSOR';
      }
    };

    const scatterplotLayer = new ScatterplotLayer({
      id: 'sensor-layer',
      data: sensors.map((s) => ({
        sensorId: s.sensorId,
        sensorType: s.sensorType,
        longitude: s.location.longitude,
        latitude: s.location.latitude
      })),
      getPosition: (d: any) => [d.longitude, d.latitude],
      getFillColor: (d: any) => getSensorTypeColor(d.sensorType || ''),
      // Scale marker size based on sector count - smaller for larger maps (25x25 = 625 sectors)
      getRadius: sectorCount > 400 ? 2.5 : sectorCount > 100 ? 3.5 : sectorCount > 25 ? 4.5 : 5,
      radiusUnits: 'pixels',
      radiusMinPixels: sectorCount > 400 ? 2 : sectorCount > 100 ? 3 : sectorCount > 25 ? 4 : 4,
      radiusMaxPixels: sectorCount > 400 ? 4 : sectorCount > 100 ? 6 : sectorCount > 25 ? 7 : 8,
      pickable: true,
    });

    const textLayer = new TextLayer({
      id: 'sensor-text-layer',
      data: sensors.map((s) => ({
        position: [s.location.longitude, s.location.latitude] as [number, number],
        text: `${getSensorTypeShortName(s.sensorType)}_${s.sensorId.toString().padStart(2, '0')}`,
      })),
      getPosition: (d: any) => d.position,
      getText: (d: any) => d.text,
      // Scale font size based on sector count - more sectors = smaller labels
      getSize: sectorCount > 100 ? 6 : sectorCount > 50 ? 7 : sectorCount > 25 ? 8 : 8,
      // Full opacity white text for maximum visibility
      getColor: [255, 255, 255, 255],
      getAngle: 0,
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'bottom',
      getPixelOffset: [0, -15],
      background: true,
      // Strong, opaque black background for better contrast
      getBackgroundColor: [0, 0, 0, 240],
      fontFamily: 'Monaco, monospace',
      fontWeight: 'bold',
      billboard: true,
    });

    return [scatterplotLayer, textLayer];
  }, [sensors, sectorCount]);

  return layers;
};
