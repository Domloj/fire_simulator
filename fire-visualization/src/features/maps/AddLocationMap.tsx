import { useEffect, useState, useMemo, useCallback } from 'react';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { MapViewState } from '@deck.gl/core';
import { useMap } from '../../components/maps/MapLibre';
import { useSelectedSectorLayer } from './useSelectedSectorLayer';
import { MainCard } from '../../components/MainCard';
import { Box, Button } from '@mui/material';
import { MapLocation } from '../../model/geography';
import { getDefaultMapLocation } from '../../model/common';
import { Sector } from '../../model/sector';
import { isPointInBounds } from '@shared/utils/isPointInBounds';

import SafeMap from '../../components/maps/SafeMap';
import DeckGL from '@deck.gl/react';

import {
  DrawPointMode,
  EditableGeoJsonLayer,
  FeatureCollection,
  Position,
  ViewMode,
} from '@deck.gl-community/editable-layers';


const parsePositionToMapLocation = (position: Position): MapLocation => ({
  longitude: position[0],
  latitude: position[1],
});

type AddLocationMapProps = {
  handleSelectedLocation: (location: MapLocation) => void;
};

// Initial state: center on Poland
const INITIAL_VIEW_STATE: MapViewState = {
  longitude: 19.945, // Kraków longitude
  latitude: 50.064652, // Kraków latitude
  zoom: 5,
};

export const AddLocationMap = ({ handleSelectedLocation }: AddLocationMapProps) => {
  const { configuration: mapConfiguration, currentSectorId } = useSelector(
    (state: RootState) => state.mapConfiguration,
  );
  
  const [currentSector, setCurrentSector] = useState<Sector | undefined>(undefined);
  useEffect(() => {
    if (currentSectorId === null) {
      setCurrentSector(undefined);
      return;
    }
    setCurrentSector(mapConfiguration.sectors.find(({ sectorId }) => sectorId === currentSectorId));
  }, [mapConfiguration, currentSectorId]);

  const [features, setFeatures] = useState<FeatureCollection>({
    type: 'FeatureCollection',
    features: [],
  });
  const [isDrawing, setIsDrawing] = useState<boolean>(false);

  const [isLocationDrawn, setIsLocationDrawn] = useState<boolean>(false);
  useEffect(() => {
    if (features.features.length === 1) {
      setIsLocationDrawn(true);
    } else {
      setIsLocationDrawn(false);
    }
  }, [features]);

  const handleEdit = useCallback(
    ({ updatedData }: { updatedData: FeatureCollection }) => {
      if (!currentSector) return;

      const featureCollection = updatedData as FeatureCollection;

      if (
        features.features.length === 0 &&
        featureCollection.features.length === 1 &&
        featureCollection.features[0].geometry.type === 'Point'
      ) {
        // Parse and save point coordinates as a location
        const locationCoords = featureCollection.features[0].geometry.coordinates as Position;
        const location = parsePositionToMapLocation(locationCoords);

        if (isPointInBounds(location, Sector.getBoundsFromContours(currentSector))) {
          setFeatures(updatedData);
          handleSelectedLocation(location);
        }
      }
    },
    [currentSector, features, handleSelectedLocation]
  );

  const drawLocationLayer = useMemo(
    () =>
      new EditableGeoJsonLayer({
        id: 'draw-location',
        data: features,
        mode: isDrawing && !isLocationDrawn ? DrawPointMode : ViewMode,
        getLineColor: [194, 13, 0, 255],
        getFillColor: [194, 13, 0, 200],
        getRadius: 10,
        getLineWidth: 3,
        pickable: true,
        selectedFeatureIndexes: [],
        updateTriggers: {
          getFillColor: [features.features.length],
          mode: [isDrawing, isLocationDrawn],
          data: [features.features.length],
        },
        onEdit: handleEdit,
      }),
    [features, isDrawing, isLocationDrawn, handleEdit]
  );

  const selectedSectorLayer = useSelectedSectorLayer(currentSector);

  const toggleDrawing = () => {
    setIsDrawing((prev) => !prev);
  };

  const handleClearSelectedLocation = () => {
    setFeatures({
      type: 'FeatureCollection',
      features: [],
    });
    handleSelectedLocation(getDefaultMapLocation()); // TODO it will be better to make same required constraint or sth
    setIsDrawing(false);
  };

  return (
    <MainCard
      hasContent={false}
      sx={{ mt: 1.5 }}
    >
      <Box sx={{ position: 'relative', width: '100%', height: '500px' /* TODO fix fixed height */ }}>
        <SafeMap
          initialCenter={[INITIAL_VIEW_STATE.longitude, INITIAL_VIEW_STATE.latitude]}
          initialZoom={INITIAL_VIEW_STATE.zoom}
        >
          <AddLocationMapInner
            currentSector={currentSector}
            isDrawing={isDrawing}
            setIsDrawing={setIsDrawing}
            selectedSectorLayer={selectedSectorLayer}
            drawLocationLayer={drawLocationLayer}
          />
        </SafeMap>
        <Box sx={{ position: 'absolute', top: 10, left: 10, zIndex: 1001 }}>
          {!isLocationDrawn ? (
            !isDrawing ? (
              <Button
                variant="contained"
                color="primary"
                onClick={toggleDrawing}
              >
                Enable selecting location
              </Button>
            ) : (
              <Button
                variant="contained"
                color="primary"
                onClick={toggleDrawing}
              >
                Disable selecting location
              </Button>
            )
          ) : (
            <Button
              variant="contained"
              color="secondary"
              onClick={handleClearSelectedLocation}
              disabled={!isLocationDrawn}
            >
              Clear selected location
            </Button>
          )}
        </Box>
      </Box>
    </MainCard>
  );
};

// Inner component that has access to map context
const AddLocationMapInner = ({
  currentSector,
  isDrawing,
  setIsDrawing,
  selectedSectorLayer,
  drawLocationLayer,
}: {
  currentSector: Sector | undefined;
  isDrawing: boolean;
  setIsDrawing: (d: boolean) => void;
  selectedSectorLayer: any;
  drawLocationLayer: EditableGeoJsonLayer;
}) => {
  const map = useMap();

  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);

  // Synchronize viewState with MapLibre
  useEffect(() => {
    if (!map) return;

    const updateViewState = () => {
      const center = map.getCenter();
      const zoom = map.getZoom();
      setViewState({
        longitude: center.lng,
        latitude: center.lat,
        zoom: zoom,
      });
    };

    updateViewState();
    map.on('move', updateViewState);

    return () => {
      map.off('move', updateViewState);
    };
  }, [map]);

  // Auto-fit to selected sector when it changes
  useEffect(() => {
    if (!map || !currentSector) return;

    try {
      const currentSectorBounds = Sector.getBoundsFromContours(currentSector);
      const sw = [currentSectorBounds.west, currentSectorBounds.south] as [number, number];
      const ne = [currentSectorBounds.east, currentSectorBounds.north] as [number, number];
      map.fitBounds([sw, ne], { padding: 80, duration: 500 });
    } catch (e) {
    }
  }, [map, currentSector]);

  // Control map interactions during drawing
  // NOTE: Panning is ALWAYS disabled - only NewConfigurationMap allows panning
  useEffect(() => {
    if (!map) return;

    // Always disable panning - only NewConfigurationMap should allow it
    map.dragPan?.disable();

    if (isDrawing) {
      // Disable all map interactions during drawing
      map.scrollZoom?.disable();
      map.boxZoom?.disable();
      map.doubleClickZoom?.disable();
      map.touchZoomRotate?.disable();
    } else {
      // Re-enable zoom interactions after drawing (but keep panning disabled)
      map.scrollZoom?.enable();
      map.boxZoom?.enable();
      map.doubleClickZoom?.enable();
      map.touchZoomRotate?.enable();
    }

    return () => {
      map.dragPan?.enable();
    };
  }, [map, isDrawing]);

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: isDrawing ? 'auto' : 'none',
        zIndex: 1002,
        background: 'transparent',
      }}
    >
      <DeckGL
        viewState={viewState}
        controller={false} /* controller must be false so EditableGeoJsonLayer can capture drag events */
        layers={[selectedSectorLayer, drawLocationLayer].filter(Boolean)}
        style={{
          pointerEvents: isDrawing ? 'auto' : 'none',
          zIndex: 1003,
          background: 'transparent',
          cursor: isDrawing ? 'crosshair' : 'default',
        }}
      />
    </div>
  );
};
