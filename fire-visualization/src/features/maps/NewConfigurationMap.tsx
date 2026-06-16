import { useEffect, useState, useMemo, useCallback } from 'react';
import { Map } from '../../components/maps/MapLibre';
import { DeckGlOverlay } from './DeckGlOverlay';
import { MainCard } from '../../components/MainCard';
import { Box, Button } from '@mui/material';
import { useFormikContext } from 'formik';
import { Configuration, getDefaultConfiguration } from '../../model/configuration';
import { Region } from '../../model/geography';
import { useSectorsLayer } from './useSectorsLayer';
import { useForestBorderLayer } from './useForestBorderLayer';
import { useMap } from '../../components/maps/MapLibre';

import {
  DrawRectangleMode,
  EditableGeoJsonLayer,
  FeatureCollection,
  Position,
  ViewMode,
} from '@deck.gl-community/editable-layers';

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
    try {
      if (!values.location || values.location.every(loc => loc.longitude === 0 && loc.latitude === 0)) {
        return null;
      }
      
      // Validate location has valid coordinates
      const hasValidLocation = values.location.every(
        loc => typeof loc.longitude === 'number' && 
               typeof loc.latitude === 'number' && 
               !isNaN(loc.longitude) && 
               !isNaN(loc.latitude) &&
               loc.longitude !== 0 && 
               loc.latitude !== 0
      );
      
      if (!hasValidLocation) {
        return null;
      }
      
      // Validate rows and columns
      const rows = Number(values.rows) || 0;
      const columns = Number(values.columns) || 0;
      
      if (rows <= 0 || columns <= 0 || rows > 100 || columns > 100) {
        return null;
      }
      
      // Generate sectors if we have location, rows, and columns
      let sectors: any[] = [];
      try {
        sectors = Configuration.createSectors({
          ...getDefaultConfiguration(),
          rows: rows,
          columns: columns,
          location: values.location,
        });
      } catch (error) {
        return null;
      }
      
      // Preprocess sectors to calculate contours from the drawn rectangle
      let preprocessedSectors: any[] = [];
      try {
        if (sectors.length > 0 && values.location) {
          preprocessedSectors = Configuration.preprocessSectors({
            ...getDefaultConfiguration(),
            rows: rows,
            columns: columns,
            location: values.location,
            sectors: sectors,
          });
          
          // Filter out sectors with invalid contours
          preprocessedSectors = preprocessedSectors.filter(
            (sector) => 
              sector && 
              sector.contours && 
              Array.isArray(sector.contours) && 
              sector.contours.length >= 3 &&
              sector.contours.every((c: any) => Array.isArray(c) && c.length >= 2 && typeof c[0] === 'number' && typeof c[1] === 'number')
          );
        }
      } catch (error) {
        // Return empty array rather than sectors without preprocessing
        preprocessedSectors = [];
      }

      // Ensure we only return configuration with valid sectors
      const validSectors = preprocessedSectors.filter(
        (sector) => 
          sector && 
          sector.contours && 
          Array.isArray(sector.contours) && 
          sector.contours.length >= 3
      );

      return {
        ...getDefaultConfiguration(),
        rows: rows,
        columns: columns,
        location: values.location,
        sectors: validSectors,
      };
    } catch (error) {
      return null;
    }
  }, [values.location, values.rows, values.columns]);

  // Get bounds from the drawn rectangle
  const bounds = useMemo(() => {
    try {
      if (!tempConfiguration) return null;
      return Configuration.getBounds(tempConfiguration);
    } catch (error) {
      return null;
    }
  }, [tempConfiguration]);


  const safeConfig = tempConfiguration || getDefaultConfiguration();
  const forestBorderLayer = useForestBorderLayer(safeConfig);
  const sectorsLayer = useSectorsLayer(safeConfig, true);

  const handleEdit = useCallback(
    ({ updatedData }: { updatedData: FeatureCollection }) => {
      try {
        
        if (!updatedData || !updatedData.features) {
          return;
        }
        
        const polygon = updatedData.features.find(
          (f) => f.geometry && f.geometry.type === 'Polygon'
        );

        
        if (!polygon || features.features.length > 0) {
          return;
        }

        if (!polygon.geometry || !polygon.geometry.coordinates || !Array.isArray(polygon.geometry.coordinates[0])) {
          return;
        }

        setFeatures(updatedData);

        const coords = (polygon.geometry.coordinates[0] as Position[]).slice(0, 4);

        if (coords.length < 4 || coords.some(c => !Array.isArray(c) || c.length < 2 || typeof c[0] !== 'number' || typeof c[1] !== 'number')) {
          return;
        }

        const lons = coords.map((c: Position) => c[0]);
        const lats = coords.map((c: Position) => c[1]);

        if (lons.some(lon => isNaN(lon) || lon < -180 || lon > 180) || 
            lats.some(lat => isNaN(lat) || lat < -90 || lat > 90)) {
          return;
        }

        const minLon = Math.min(...lons);
        const maxLon = Math.max(...lons);
        const minLat = Math.min(...lats);
        const maxLat = Math.max(...lats);

        if (minLon >= maxLon || minLat >= maxLat) {
          return;
        }

        const region: Region = [
          { longitude: minLon, latitude: minLat }, // SW
          { longitude: maxLon, latitude: minLat }, // SE
          { longitude: maxLon, latitude: maxLat }, // NE
          { longitude: minLon, latitude: maxLat }, // NW
        ];

        setFieldValue('location', region);

        setIsDrawing(false);
      } catch (error) {
        setIsDrawing(false);
      }
    },
    [features, setFieldValue, isDrawing]
  );

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
        selectedFeatureIndexes: [],
        getLineColor: [255, 0, 0, 255],
        getFillColor: [255, 0, 0, 60],
        getTentativeLineColor: [255, 255, 0, 255],
        getTentativeFillColor: [255, 255, 0, 120],
        getLineWidth: 2,
      });
    },
    [features, isDrawing, handleEdit]
  );

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
            tempConfiguration={tempConfiguration}
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
              <Button variant="contained" color="warning" onClick={stopDrawing}>
                Stop Drawing
              </Button>
            ) : (
              <Button variant="contained" onClick={startDrawing}>
                Start Drawing
              </Button>
            )
          ) : (
            <Button variant="contained" color="secondary" onClick={clear}>
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
  tempConfiguration,
}: {
  features: FeatureCollection;
  setFeatures: (f: FeatureCollection) => void;
  isDrawing: boolean;
  setIsDrawing: (d: boolean) => void;
  handleEdit: (args: { updatedData: FeatureCollection }) => void;
  layer: EditableGeoJsonLayer;
  forestBorderLayer: any;
  sectorsLayer: any;
  tempConfiguration: Configuration | null;
}) => {
  const map = useMap('new-config-map');

  /* ---------------- Adjust map interactions while drawing ---------------- */
  useEffect(() => {
    if (!map) {
      return;
    }

    const interactions = [
      map.dragPan,
      map.scrollZoom,
      map.boxZoom,
      map.doubleClickZoom,
      map.touchZoomRotate,
    ];

    if (isDrawing) {
      // Disable pan when drawing, but keep zoom enabled for navigation
      map.dragPan?.disable();
      // Keep other interactions enabled (zoom, etc.)
    } else {
      // Enable all interactions when not drawing
      interactions.forEach((i) => i?.enable());
    }

    return () => {
      // Always re-enable all interactions on cleanup
      interactions.forEach((i) => i?.enable());
    };
  }, [map, isDrawing]);

  // Debug: Log overlay rendering
  useEffect(() => {
  }, [isDrawing, layer]);

  // Only render sectors if we have valid sectors with contours
  const hasValidSectors = tempConfiguration && 
                          tempConfiguration.sectors && 
                          tempConfiguration.sectors.length > 0 &&
                          tempConfiguration.sectors.some((s: any) => s.contours && Array.isArray(s.contours) && s.contours.length >= 3);

  return (
    <>
      {/* DeckGL overlay for drawing - always rendered so polygon stays visible */}
      <DeckGlOverlay 
        overlayId="drawing" 
        layers={[layer]} 
        capturePointerEvents={isDrawing}
      />
      
      {/* DeckGL overlay for sectors and forest border - only if we have valid sectors */}
      {hasValidSectors && forestBorderLayer && (
        <DeckGlOverlay
          overlayId="sectors"
          layers={[
            forestBorderLayer,
            ...(Array.isArray(sectorsLayer) ? sectorsLayer : sectorsLayer ? [sectorsLayer] : []),
          ].filter(Boolean)}
        />
      )}
    </>
  );
};
