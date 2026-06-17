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
import { Grid, Box, Typography, IconButton } from '@mui/material';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import FitScreenIcon from '@mui/icons-material/FitScreen';
import { MainCard } from '../MainCard';
import React, { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AgentMarkerManager from './AgentMarkerManager';
import { useLocation } from 'react-router-dom';
import { Configuration } from '../../model/configuration';
import { agentPositionController } from '../../features/maps/AgentPositionController';

import { eventEmitter } from '@shared/utils/eventEmitter';
import { useForesterPatrolLayer } from '../../features/maps/useForesterPatrolLayer';
import { useSensorLayer } from '../../features/maps/useSensorLayer';
import { useCameraLayer } from '../../features/maps/useCameraLayer';
import { useForestBorderLayer } from '../../features/maps/useForestBorderLayer';
import { useSectorsLayer } from '../../features/maps/useSectorsLayer';
import { useSelectedSectorLayer } from '../../features/maps/useSelectedSectorLayer';
import { useOnSectorChange } from '../../features/maps/useOnSectorChange';
import { useOnTooltipChange } from '../../features/maps/useOnTooltipChange';
import { useDispatch, useSelector, shallowEqual } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { setCurrentSectorId } from '../../store/mapConfigurationSlice';
import FireBrigadeDialog from '../simulation/FireBrigadeDialog';
import { FireBrigade } from '../../model/FireBrigade';
import { ForesterPatrol } from '../../model/ForesterPatrol';

const getSectorCenter = (contours: number[][]): [number, number] | null => {
  if (!contours || contours.length === 0) return null;
  let sumLon = 0;
  let sumLat = 0;
  for (const point of contours) {
    sumLon += point[0];
    sumLat += point[1];
  }
  return [sumLon / contours.length, sumLat / contours.length];
};

const getAgentDestination = (
  agent: FireBrigade | ForesterPatrol,
  sectors: any[],
): [number, number] | null => {
  if (agent.state !== 'TRAVELLING') return null;

  const loc = (agent as any).currentLocation;
  if (!loc || typeof loc.longitude !== 'number' || typeof loc.latitude !== 'number') {
    return null;
  }

  if (agent.sectorId && agent.sectorId > 0) {
    const sector = sectors.find((s: any) => s.sectorId === agent.sectorId);
    if (sector?.contours?.length) {
      const center = getSectorCenter(sector.contours);
      if (center) {
        const dx = center[0] - loc.longitude;
        const dy = center[1] - loc.latitude;
        if (Math.hypot(dx, dy) > 0.001) {
          return center;
        }
      }
    }
  }
  const dx = agent.baseLocation.longitude - loc.longitude;
  const dy = agent.baseLocation.latitude - loc.latitude;
  if (Math.hypot(dx, dy) > 0.001) {
    return [agent.baseLocation.longitude, agent.baseLocation.latitude];
  }
  return null;
};

const buildAgentHistoryGeojson = (
  history: {
    fireBrigades: Record<number, [number, number][]>;
    foresterPatrols: Record<number, [number, number][]>;
  },
) => {
  const features: any[] = [];

  Object.entries(history.fireBrigades).forEach(([id, points]) => {
    if (points.length < 2) return;
    features.push({
      type: 'Feature',
      properties: { color: '#cc0000' },
      geometry: {
        type: 'LineString',
        coordinates: points,
      },
    });
  });

  Object.entries(history.foresterPatrols).forEach(([id, points]) => {
    if (points.length < 2) return;
    features.push({
      type: 'Feature',
      properties: { color: '#0044cc' },
      geometry: {
        type: 'LineString',
        coordinates: points,
      },
    });
  });

  return {
    type: 'FeatureCollection',
    features,
  };
};

export const MainMap = () => {
  const location = useLocation();
  const mapConfiguration = useSelector((state: RootState) => state.mapConfiguration.configuration);
  const currentSectorId = useSelector((state: RootState) => state.mapConfiguration.currentSectorId);
  const renderCountRef = useRef(0);
  const lastRenderLogTimeRef = useRef(Date.now());
  const dispatch = useDispatch();
  const [tooltip, setTooltip] = useState<ReactNode>(null);

  const [bounds, setBounds] = useState(() => {
    if (!mapConfiguration || !mapConfiguration.location) {
      return { north: 0, east: 0, south: 0, west: 0 };
    }
    return Configuration.getBounds(mapConfiguration);
  });

  const isConfigView = !location.pathname.includes('/simulation');

  useEffect(() => {
    if (!mapConfiguration || !mapConfiguration.location) {
      return;
    }
    const newBounds = Configuration.getBounds(mapConfiguration);
    if (
      newBounds.north !== bounds.north ||
      newBounds.south !== bounds.south ||
      newBounds.east !== bounds.east ||
      newBounds.west !== bounds.west
    ) {
      setBounds(newBounds);
    }
  }, [mapConfiguration, bounds]); // Include bounds in dependencies for comparison

  const forestBorderLayer = useForestBorderLayer(mapConfiguration);
  const sectorsLayer = useSectorsLayer(mapConfiguration, false, undefined, currentSectorId);
  const selectedSectorLayer = useSelectedSectorLayer(
    mapConfiguration.sectors.find(({ sectorId }) => sectorId === currentSectorId),
  );

  const foresterPatrolLayer = useForesterPatrolLayer();
  const sensorLayer = useSensorLayer();
  const cameraLayer = useCameraLayer();

  const [showAgentHistory, setShowAgentHistory] = useState(false);

  const [historyVersion, setHistoryVersion] = useState(0);
  const historyRef = useRef<{
    fireBrigades: Record<number, [number, number][]>;
    foresterPatrols: Record<number, [number, number][]>;
  }>({ fireBrigades: {}, foresterPatrols: {} });

  const agentHistoryGeojson = { type: 'FeatureCollection', features: [] };

  useEffect(() => {
    const onToggle = (next?: boolean) => {
      setShowAgentHistory((prev) => (typeof next === 'boolean' ? next : !prev));
    };
    eventEmitter.addListener('toggleAgentHistory', onToggle);
    return () => {
      eventEmitter.removeListener('toggleAgentHistory', onToggle);
    };
  }, []);

  const lastPositionsRef = useRef<{
    fireBrigades: Record<number, [number, number]>;
    foresterPatrols: Record<number, [number, number]>;
  }>({ fireBrigades: {}, foresterPatrols: {} });

  // Metrics: track position update frequency on frontend
  const positionUpdateMetricsRef = useRef({
    count: 0,
    windowStart: Date.now(),
    lastLogTime: Date.now(),
  });

  // FIX: Subscribe to agentPositionController for real-time position updates
  // instead of relying on mapConfiguration dependency (which changes rarely)
  useEffect(() => {
    if (!showAgentHistory) {
      return;
    }

    const maxPoints = 500;
    const MIN_POSITION_CHANGE = 0.0001;

    const unsubscribe = agentPositionController.subscribe((positions) => {
      let changed = false;
      const now = Date.now();

      // Metrics: count position updates
      positionUpdateMetricsRef.current.count++;
      const window = now - positionUpdateMetricsRef.current.windowStart;
      if (window >= 60000) { // Log every minute
        const updatesPerSec = positionUpdateMetricsRef.current.count / (window / 1000);
        const updatesPerMin = positionUpdateMetricsRef.current.count;
        console.log(
          `[FRONTEND-METRICS] Agent position updates: ${positionUpdateMetricsRef.current.count} in ${(window / 1000).toFixed(1)}s (${updatesPerSec.toFixed(1)} / sec, ${updatesPerMin} / min)`
        );
        positionUpdateMetricsRef.current.count = 0;
        positionUpdateMetricsRef.current.windowStart = now;
      }

      // Process all agents from positions snapshot
      for (const [key, pos] of positions.entries()) {
        if (!pos || !pos.lng || !pos.lat) continue;

        const parts = key.split(':');
        if (parts.length < 2) continue;

        const unitType = parts[0];
        const id = parseInt(parts[1], 10);
        if (!Number.isFinite(id)) continue;

        const point: [number, number] = [pos.lng, pos.lat];

        if (unitType === 'fireBrigade') {
          const list = historyRef.current.fireBrigades[id] || [];
          const lastPosition = lastPositionsRef.current.fireBrigades[id];

          if (!lastPosition || Math.hypot(lastPosition[0] - point[0], lastPosition[1] - point[1]) > MIN_POSITION_CHANGE) {
            list.push(point);
            if (list.length > maxPoints) list.shift();
            historyRef.current.fireBrigades[id] = list;
            lastPositionsRef.current.fireBrigades[id] = point;
            changed = true;
          }
        } else if (unitType === 'foresterPatrol') {
          const list = historyRef.current.foresterPatrols[id] || [];
          const lastPosition = lastPositionsRef.current.foresterPatrols[id];

          if (!lastPosition || Math.hypot(lastPosition[0] - point[0], lastPosition[1] - point[1]) > MIN_POSITION_CHANGE) {
            list.push(point);
            if (list.length > maxPoints) list.shift();
            historyRef.current.foresterPatrols[id] = list;
            lastPositionsRef.current.foresterPatrols[id] = point;
            changed = true;
          }
        }
      }

      if (changed) {
        setHistoryVersion((v) => v + 1);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [showAgentHistory]);

  useOnTooltipChange(setTooltip);
  useEffect(() => {
    const onClick = (brigade: any) => {
      // show a small tooltip as confirmation; other components can subscribe to 'onFireBrigadeClick'
      const tooltip = (
        <div style={{ padding: '6px', background: 'rgba(0,0,0,0.75)', color: 'white', borderRadius: 4 }}>
          Send brigade: {brigade.fireBrigadeId}
        </div>
      );
      // emit tooltip via existing mechanism
      try {
        eventEmitter.emit('onTooltipChange', tooltip);
      } catch (e) {
        // pass
      }
    };

    eventEmitter.addListener('onFireBrigadeClick', onClick);
    return () => {
      eventEmitter.removeListener('onFireBrigadeClick', onClick);
    };
  }, []);

  const onSectorChange = useCallback(
    (sectorId: number | null) => {
      try {
        dispatch(setCurrentSectorId({ currentSectorId: sectorId }));
      } catch (error) {
        // throw error;
      }
    },
    [dispatch],
  );
  useOnSectorChange(onSectorChange);

  if (Object.values(bounds).every((bound) => bound === 0))
    return (
      <Box
        sx={{
          width: '100%',
          height: isConfigView ? '100%' : '800px',
          position: 'relative',
        }}
      >
        <MainCard
          hasContent={false}
          hasBorder={false}
          sx={{
            width: '100%',
            height: '100%',
            margin: 0,
            padding: 0,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              backgroundColor: 'secondary.light',
              width: '100%',
              height: '100%',
            }}
          >
            <Typography variant="h2">No configuration selected!</Typography>
            <Typography variant="h4">Please select a configuration to see the map</Typography>
          </Box>
        </MainCard>
      </Box>
    );

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'hidden',
        flex: 1,
        minHeight: 0,
        paddingTop: '64px',
        boxSizing: 'border-box',
      }}
    >
      <MainCard
        hasContent={false}
        hasBorder={false}
        sx={{
          overflow: 'hidden',
          width: '100%',
          height: '100%',
          flex: 1,
          minHeight: 0,
          margin: 0,
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 0,
          '&.main-card': {
            borderRadius: 0,
          },
        }}
      >
        <Box sx={{
          width: '100%',
          height: '100%',
          position: 'relative',
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <Map
            id="main-map"
            defaultBounds={bounds || { north: 0, east: 0, south: 0, west: 0 }}
            onDragstart={() => {
              // hide tooltip when dragging the map
              if (tooltip !== null) setTooltip(null);
            }}
          >
            <MainMapInner
              tooltip={tooltip}
              bounds={bounds}
              forestBorderLayer={forestBorderLayer}
              sectorsLayer={sectorsLayer}
              selectedSectorLayer={selectedSectorLayer}

              foresterPatrolLayer={foresterPatrolLayer}
              sensorLayer={sensorLayer}
              cameraLayer={cameraLayer}
              agentHistoryGeojson={agentHistoryGeojson}
              showAgentHistory={showAgentHistory}
              currentSectorId={currentSectorId}
              isConfigView={isConfigView}
            />
          </Map>
        </Box>
      </MainCard>
    </Box>
  );
};

type MainMapInnerProps = {
  tooltip: ReactNode;
  bounds: ReturnType<typeof Configuration.getBounds>;
  forestBorderLayer: any;
  sectorsLayer: any;
  selectedSectorLayer: any;

  foresterPatrolLayer: any;
  sensorLayer: any;
  cameraLayer: any;
  agentHistoryGeojson: any;
  showAgentHistory: boolean;
  currentSectorId: number | null;
  isConfigView: boolean;
};

const MainMapInner = ({
  tooltip,
  bounds,
  forestBorderLayer,
  sectorsLayer,
  selectedSectorLayer,

  foresterPatrolLayer,
  sensorLayer,
  cameraLayer,
  agentHistoryGeojson,
  showAgentHistory,
  currentSectorId,
  isConfigView,
}: MainMapInnerProps) => {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    const sourceId = 'agent-history';
    const layerId = 'agent-history-line';

    const ensureLayer = () => {
      // Safety check: ensure map is loaded and style is ready
      if (!map || !map.loaded || !map.getStyle) return;
      try {
        const style = map.getStyle();
        if (!style || !style.version) return; // Style not ready yet
      } catch (e) {
        // Style not ready, wait for next event
        return;
      }

      const source = map.getSource(sourceId) as any;
      if (source) {
        source.setData(agentHistoryGeojson);
      } else {
        try {
          map.addSource(sourceId, {
            type: 'geojson',
            data: agentHistoryGeojson,
          });
        } catch (e) {
          // Source might already exist, continue
        }
      }

      if (!map.getLayer(layerId)) {
        try {
          map.addLayer({
            id: layerId,
            type: 'line',
            source: sourceId,
            layout: {
              'line-join': 'round',
              'line-cap': 'round',
              'visibility': showAgentHistory ? 'visible' : 'none',
            },
            paint: {
              'line-color': ['get', 'color'],
              'line-width': 2.5,
              'line-opacity': 0.75,
            },
          });
        } catch (e) {
          // Layer might already exist or source not ready
        }
      } else {
        map.setLayoutProperty(layerId, 'visibility', showAgentHistory ? 'visible' : 'none');
      }
    };

    // Wait for map to be fully loaded before adding layers
    if (map.loaded) {
      ensureLayer();
    } else {
      map.once('load', ensureLayer);
    }
    map.on?.('styledata', ensureLayer);
    map.on?.('load', ensureLayer);

    return () => {
      map.off?.('styledata', ensureLayer);
      map.off?.('load', ensureLayer);
    };
  }, [map, agentHistoryGeojson, showAgentHistory]);

  // Disable panning in MainMap - only NewConfigurationMap should allow panning
  // But allow clicks and hovers for sector selection
  useEffect(() => {
    if (!map) return;

    // Disable panning but keep other interactions enabled
    map.dragPan?.disable();

    // Ensure zoom and other interactions still work
    map.scrollZoom?.enable();
    map.boxZoom?.enable();
    map.doubleClickZoom?.enable();
    map.touchZoomRotate?.enable();

    return () => {
      map.dragPan?.enable();
    };
  }, [map]);

  // Recalculate map bounds when sector selection changes or container resizes (in config view)
  useEffect(() => {
    if (!map || !isConfigView || !bounds || Object.values(bounds).every((bound) => bound === 0)) return;

    // Resize map first to account for container size changes
    map.resize();

    // Small delay to ensure resize has taken effect
    const timeoutId = setTimeout(() => {
      const sw = [bounds.west, bounds.south] as [number, number];
      const ne = [bounds.east, bounds.north] as [number, number];
      map.fitBounds([sw, ne], {
        duration: 0,
        padding: {
          top: 50,
          bottom: 100,
          left: 50,
          right: 50
        }
      });
    }, 100);

    return () => clearTimeout(timeoutId);
  }, [map, bounds, currentSectorId, isConfigView]);

  return (
    <>
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          pointerEvents: 'none',
          zIndex: 1000,
          width: '100%',
          height: '100%',
        }}
      >
        {tooltip}
      </div>
      <div
        style={{
          position: 'absolute',
          top: 12,
          right: 12,
          zIndex: 1100,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          pointerEvents: 'auto',
        }}
      >
        <IconButton
          size="small"
          onClick={() => {
            if (!map) return;
            const current = map.getZoom();
            map.easeTo({ zoom: current + 1 });
          }}
          sx={{ color: 'red' }}
          aria-label="Zoom in"
        >
          <ZoomInIcon />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => {
            if (!map) return;
            const current = map.getZoom();
            map.easeTo({ zoom: current - 1 });
          }}
          sx={{ color: 'red' }}
          aria-label="Zoom out"
        >
          <ZoomOutIcon />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => {
            if (map) {
              const sw = [bounds.west, bounds.south] as [number, number];
              const ne = [bounds.east, bounds.north] as [number, number];
              map.fitBounds([sw, ne], {
                padding: {
                  top: 50,
                  bottom: 100, // Increased bottom padding to show lower sectors
                  left: 50,
                  right: 50
                }
              });
            }
          }}
          sx={{ color: 'red' }}
          aria-label="Fit bounds"
        >
          <FitScreenIcon />
        </IconButton>
      </div>
      <DeckGlOverlay
        overlayId="main-map"
        capturePointerEvents={true} // Enable pointer events for sector hover/click
        layers={[
          forestBorderLayer,
          ...(Array.isArray(sectorsLayer) ? sectorsLayer : [sectorsLayer]),
          selectedSectorLayer,

          ...(Array.isArray(foresterPatrolLayer) ? foresterPatrolLayer : [foresterPatrolLayer]),
          ...(Array.isArray(sensorLayer) ? sensorLayer : [sensorLayer]),
          ...(Array.isArray(cameraLayer) ? cameraLayer : [cameraLayer]),
        ].filter(Boolean)}
      />
      {/* Agent markers updated directly on MapLibre for high-frequency updates */}
      {!isConfigView && <AgentMarkerManager />}
    </>
  );
};

