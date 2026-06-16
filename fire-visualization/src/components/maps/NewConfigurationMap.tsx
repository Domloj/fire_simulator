import { useEffect, useState, useMemo, useCallback } from 'react';

// Maps
import SafeMap from './SafeMap';
import { Map } from './MapLibre';
import { DeckGlOverlay } from './DeckGlOverlay';
import {
  DrawRectangleMode,
  EditableGeoJsonLayer,
  FeatureCollection,
  Position,
  ViewMode,
} from '@deck.gl-community/editable-layers';

// UI
import { MainCard } from '../MainCard';
import { Box, Button } from '@mui/material';

// Form
import { useFormikContext } from 'formik';

// Types & Hooks
import { Configuration, getDefaultConfiguration } from '../../model/configuration';
import { Region } from '../../model/geography';
import { useSectorsLayer } from '../../features/maps/useSectorsLayer';
import { useForestBorderLayer } from '../../features/maps/useForestBorderLayer';
import { useMap } from './MapLibre';

// Initial map view (Kraków)
const INITIAL_CENTER: [number, number] = [19.945, 50.064652];
const INITIAL_ZOOM = 5;

export const NewConfigurationMap = () => {
  const { values, setFieldValue } = useFormikContext<Configuration>();

  const [features, setFeatures] = useState<FeatureCollection>({
    type: 'FeatureCollection',
    features: [],
  });
  const [isDrawing, setIsDrawing] = useState(false);

  // Debug: Log isDrawing changes
  useEffect(() => {
  }, [isDrawing]);

  // Create a temporary configuration for sector visualization
  const tempConfiguration = useMemo(() => {
    if (!values.location || values.location.every(loc => loc.longitude === 0 && loc.latitude === 0)) {
      return null;
    }
    
    // Generate sectors if we have location, rows, and columns
    const sectors = values.rows > 0 && values.columns > 0 
      ? Configuration.createSectors({
          ...getDefaultConfiguration(),
          rows: values.rows,
          columns: values.columns,
          location: values.location,
        })
      : [];
    
    // Preprocess sectors to calculate contours from the drawn rectangle
    const preprocessedSectors = sectors.length > 0 && values.location
      ? Configuration.preprocessSectors({
          ...getDefaultConfiguration(),
          rows: values.rows,
          columns: values.columns,
          location: values.location,
          sectors: sectors,
        })
      : [];

    return {
      ...getDefaultConfiguration(),
      rows: values.rows,
      columns: values.columns,
      location: values.location,
      sectors: preprocessedSectors,
    };
  }, [values.location, values.rows, values.columns]);

  // Get bounds from the drawn rectangle
  const bounds = useMemo(() => {
    if (!tempConfiguration) return null;
    return Configuration.getBounds(tempConfiguration);
  }, [tempConfiguration]);

  // Sector layers (like MainMap) - only render when we have a valid configuration
  const forestBorderLayer = useForestBorderLayer(tempConfiguration || getDefaultConfiguration());
  const sectorsLayer = tempConfiguration ? useSectorsLayer(tempConfiguration, true) : null;

  /* ---------------- Handle rectangle creation ---------------- */
  const handleEdit = useCallback(
    ({ updatedData }: { updatedData: FeatureCollection }) => {
      
      const polygon = updatedData.features.find(
        (f) => f.geometry.type === 'Polygon'
      );

      
      if (!polygon || features.features.length > 0) {
        return;
      }

      setFeatures(updatedData);

      const coords = (polygon.geometry.coordinates[0] as Position[]).slice(0, 4);

      const lons = coords.map((c: Position) => c[0]);
      const lats = coords.map((c: Position) => c[1]);

      const minLon = Math.min(...lons);
      const maxLon = Math.max(...lons);
      const minLat = Math.min(...lats);
      const maxLat = Math.max(...lats);

      const region: Region = [
        { longitude: minLon, latitude: minLat }, // SW
        { longitude: maxLon, latitude: minLat }, // SE
        { longitude: maxLon, latitude: maxLat }, // NE
        { longitude: minLon, latitude: maxLat }, // NW
      ];

      setFieldValue('location', region);

      setIsDrawing(false);
    },
    [features, setFieldValue]
  );

  /* ---------------- DeckGL Layer ---------------- */
  const layer = useMemo(
    () => {
      const mode = isDrawing ? DrawRectangleMode : ViewMode;
      return new EditableGeoJsonLayer({
        id: 'draw-forest-bounds',
        data: features,
        mode: mode,
        onEdit: handleEdit,
        pickable: true,
        autoHighlight: isDrawing,
        selectedFeatureIndexes: [], // Required prop to prevent undefined errors
        getLineColor: [255, 0, 0, 255],
        getFillColor: [255, 0, 0, 60],
        getTentativeLineColor: [255, 255, 0, 255],
        getTentativeFillColor: [255, 255, 0, 120],
        getLineWidth: 2,
      });
    },
    [features, isDrawing, handleEdit]
  );

  /* ---------------- Actions ---------------- */
  const startDrawing = () => {
    setIsDrawing(true);
  };
  
  const stopDrawing = () => {
    setIsDrawing(false);
  };

  const clear = () => {
    setFeatures({ type: 'FeatureCollection', features: [] });
    setFieldValue('location', getDefaultConfiguration().location);
    setIsDrawing(false);
  };

  /* ---------------- Render ---------------- */
  return (
    <MainCard hasContent={false} sx={{ mt: 1.5 }}>
      <Box sx={{ position: 'relative', width: '100%', height: 500 }}>
        <Map
          id="new-config-map"
          defaultBounds={bounds || undefined}
          initialCenter={bounds ? undefined : INITIAL_CENTER}
          initialZoom={bounds ? undefined : INITIAL_ZOOM}
        >
          <NewConfigurationMapInner
            features={features}
            setFeatures={setFeatures}
            isDrawing={isDrawing}
            setIsDrawing={setIsDrawing}
            handleEdit={handleEdit}
            layer={layer}
            forestBorderLayer={forestBorderLayer}
            sectorsLayer={sectorsLayer}
          />
        </Map>

        {/* Controls - Always on top and clickable */}
        <Box 
          sx={{ 
            position: 'absolute', 
            top: 10, 
            left: 10, 
            zIndex: 10001,
            pointerEvents: 'none', // Don't block map events
            '& > *': {
              pointerEvents: 'auto', // But allow button clicks
            }
          }}
        >
          {features.features.length === 0 ? (
            isDrawing ? (
              <Button 
                variant="contained" 
                color="warning" 
                onClick={stopDrawing}
              >
                Stop Drawing
              </Button>
            ) : (
              <Button 
                variant="contained" 
                onClick={startDrawing}
              >
                Start Drawing
              </Button>
            )
          ) : (
            <Button 
              variant="contained" 
              color="secondary" 
              onClick={clear}
            >
              Clear Forest Bounds
            </Button>
          )}
        </Box>
      </Box>
    </MainCard>
  );
};

// Inner component that has access to map context
const NewConfigurationMapInner = ({
  features,
  setFeatures,
  isDrawing,
  setIsDrawing,
  handleEdit,
  layer,
  forestBorderLayer,
  sectorsLayer,
}: {
  features: FeatureCollection;
  setFeatures: (f: FeatureCollection) => void;
  isDrawing: boolean;
  setIsDrawing: (d: boolean) => void;
  handleEdit: (args: { updatedData: FeatureCollection }) => void;
  layer: EditableGeoJsonLayer;
  forestBorderLayer: any;
  sectorsLayer: any;
}) => {
  const map = useMap('new-config-map');

  /* ---------------- Adjust map interactions while drawing ---------------- */
  useEffect(() => {
    if (!map) {
      return;
    }

    // Only disable dragPan when drawing - allow zoom so users can navigate
    // DeckGL will handle drawing interactions
    if (isDrawing) {
      map.dragPan?.disable();
    } else {
      map.dragPan?.enable();
    }

    return () => {
      map.dragPan?.enable();
    };
  }, [map, isDrawing]);

  // Debug: Log overlay rendering
  useEffect(() => {
  }, [isDrawing, layer]);

  return (
    <>
      {/* DeckGL overlay for drawing - capture events when drawing */}
      <DeckGlOverlay 
        overlayId="drawing" 
        layers={[layer]} 
        capturePointerEvents={isDrawing}
      />
      
      {/* DeckGL overlay for sectors and forest border */}
      <DeckGlOverlay
        overlayId="sectors"
        layers={[
          forestBorderLayer,
          ...(Array.isArray(sectorsLayer) ? sectorsLayer : [sectorsLayer]),
        ].filter(Boolean)}
      />
    </>
  );
};
