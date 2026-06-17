import SafeMap from './SafeMap';
import DeckGL from '@deck.gl/react';

import { useEffect, useState, useMemo } from 'react';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { MapViewState } from '@deck.gl/core';
import { useMap } from './MapLibre';
import { useSelectedSectorLayer } from '../../features/maps/useSelectedSectorLayer';
import { ProcessedSector } from '../../model/processedSector';
import { MainCard } from '../MainCard';
import { Box, Button } from '@mui/material';
import { MapLocation } from '../../model/geography';
import { getDefaultMapLocation } from '../../model/common';
import { Sector } from '../../model/sector';
import { isPointInBounds } from '@shared/utils/isPointInBounds';

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

// Why is this mocked? IDK! 
const INITIAL_VIEW_STATE: MapViewState = {
  longitude: 19.945, 
  latitude: 50.064652, 
  zoom: 5,
};

const AddLocationMapInner = ({
  viewState,
  setViewState,
  currentSector,
  isDrawing,
  setIsDrawing,
  selectedSectorLayer,
  drawLocationLayer,
}: {
  viewState: MapViewState;
  setViewState: (vs: MapViewState) => void;
  currentSector: Sector | undefined;
  isDrawing: boolean;
  setIsDrawing: (d: boolean) => void;
  selectedSectorLayer: any;
  drawLocationLayer: EditableGeoJsonLayer;
}) => {
  const map = useMap();

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
  }, [map, setViewState]);

  useEffect(() => {
    if (!map || !currentSector) return;

    try {
      const currentSectorBounds = Sector.getBoundsFromContours(currentSector);
      const sw = [currentSectorBounds.west, currentSectorBounds.south] as [number, number];
      const ne = [currentSectorBounds.east, currentSectorBounds.north] as [number, number];
      map.fitBounds([sw, ne], { padding: 80, duration: 500 });
    } catch (e) {
      // pass
    }
  }, [map, currentSector]);


  useEffect(() => {
    if (!map) return;

    map.dragPan?.disable();

    if (isDrawing) {
      map.scrollZoom?.disable();
      map.boxZoom?.disable();
      map.doubleClickZoom?.disable();
      map.touchZoomRotate?.disable();
    } else {
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
    <div style={{ 
      position: 'absolute', 
      top: 0, 
      left: 0, 
      width: '100%', 
      height: '100%', 
      pointerEvents: isDrawing ? 'auto' : 'none', 
      zIndex: 1002, 
      background: 'transparent' 
    }}>
      <DeckGL
        viewState={viewState}
        controller={false}
        layers={[selectedSectorLayer, drawLocationLayer].filter(Boolean)}
        style={{ 
          pointerEvents: isDrawing ? 'auto' : 'none', 
          zIndex: '1003', 
          background: 'transparent', 
          cursor: isDrawing ? 'crosshair' : 'default' 
        }}
      />
    </div>
  );
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

  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE);

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

  const drawLocationLayer = useMemo(() => new EditableGeoJsonLayer({
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
    onEdit: ({ updatedData }) => {
      if (!currentSector) return;

      const featureCollection = updatedData as FeatureCollection;

      if (
        features.features.length === 0 &&
        featureCollection.features.length === 1 &&
        featureCollection.features[0].geometry.type === 'Point'
      ) {
        const locationCoords = featureCollection.features[0].geometry.coordinates as Position;
        const location = parsePositionToMapLocation(locationCoords);

        if (isPointInBounds(location, Sector.getBoundsFromContours(currentSector))) {
          setFeatures(updatedData);
          handleSelectedLocation(location);
        }
      }
    },
  }), [features, isDrawing, isLocationDrawn, currentSector, handleSelectedLocation]);

  const selectedSectorLayer = useSelectedSectorLayer(currentSector as ProcessedSector | undefined);

  const toggleDrawing = () => {
    setIsDrawing((prev) => !prev);
  };

  const handleClearSelectedLocation = () => {
    setFeatures({
      type: 'FeatureCollection',
      features: [],
    });
    handleSelectedLocation(getDefaultMapLocation()); 
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
            viewState={viewState}
            setViewState={setViewState}
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
