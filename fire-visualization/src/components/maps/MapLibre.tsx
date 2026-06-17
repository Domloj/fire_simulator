import React, { PropsWithChildren, useEffect, useMemo, useRef, useState, createContext, useContext } from 'react';
import maplibre from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

export type MapProps = {
  id?: string;
  defaultBounds?: { north: number; east: number; south: number; west: number };
  initialCenter?: [number, number];
  initialZoom?: number;
  onDragstart?: () => void;
  style?: React.CSSProperties;
};

type MapContextValue = {
  map: maplibregl.Map | null;
  id?: string;
};

const MapContext = createContext<MapContextValue | null>(null);

export const Map = (props: PropsWithChildren<MapProps> = {}) => {
  // Safety check: ensure props is defined (provide defaults)
  if (!props || typeof props !== 'object') {
    console.error('[MapLibre] Map component received invalid props:', props);
    return null;
  }
  const { children, id, defaultBounds, initialCenter, initialZoom, onDragstart, style } = props;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const mapInstance = new maplibre.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'esri-satellite': {
            type: 'raster',
            tiles: [
              'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
            ],
            tileSize: 256,
            attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
          }
        },
        layers: [
          {
            id: 'esri-satellite-layer',
            type: 'raster',
            source: 'esri-satellite',
            minzoom: 0,
            maxzoom: 22,
            paint: {
              'raster-opacity': 1,
              'raster-fade-duration': 0
            }
          }
        ]
      },
      center: initialCenter ?? [0, 0],
      zoom: initialZoom ?? 1,
      maxZoom: 22,
      preserveDrawingBuffer: true, // Prevent WebGL context loss
      failIfMajorPerformanceCaveat: false,
      // OPTIMIZATION: Reduce memory usage and improve performance
      refreshExpiredTiles: false,
      maxTileCacheSize: 200, // Increased to prevent tile thrashing while maintaining perf
      trackResize: true,
      // CRITICAL: Disable map animations and transitions for blazing fast rendering
      antialias: false, // Disable antialiasing - faster rendering
      // Reduce style evaluation frequency
      fadeDuration: 0, // No fade animation on tiles
      crossSourceCollisions: false, // Disable collision detection between sources
    });

    mapInstance.on('movestart', () => {
      if (onDragstart) onDragstart();
    });

    // Add error handling for WebGL context loss
    mapInstance.on('webglcontextlost', (e) => {
      e.preventDefault();
      console.warn('[MapLibre] WebGL context lost - attempting to restore...');
    });

    mapInstance.on('webglcontextrestored', () => {
      // logging removed for performance
    });

    setMap(mapInstance);

    // Ensure the map is resized when the container changes size (prevents trimmed/zoomed view)
    // Use ResizeObserver with rAF throttling to avoid flicker/blank flash on rapid resizes
    let lastWidth = 0;
    let lastHeight = 0;
    let resizeRaf: number | null = null;
    let resizeTimer: number | null = null;

    const scheduleResize = () => {
      if (resizeTimer !== null) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(() => {
        if (resizeRaf !== null) {
          cancelAnimationFrame(resizeRaf);
        }
        resizeRaf = requestAnimationFrame(() => {
          resizeRaf = null;
          const el = containerRef.current;
          if (!el) return;
          const { clientWidth, clientHeight } = el;
          if (clientWidth === lastWidth && clientHeight === lastHeight) return;
          lastWidth = clientWidth;
          lastHeight = clientHeight;
          try {
            mapInstance.resize();
          } catch (err) {
            // pass
          }
        });
      }, 120);
    };

    const ro = new ResizeObserver(() => {
      scheduleResize();
    });
    if (containerRef.current) ro.observe(containerRef.current);

    // Some browsers may layout late, ensure initial correct sizing
    setTimeout(() => scheduleResize(), 0);

    const onWindowResize = () => scheduleResize();
    window.addEventListener('resize', onWindowResize);

    return () => {
      window.removeEventListener('resize', onWindowResize);
      ro.disconnect();
      if (resizeRaf !== null) cancelAnimationFrame(resizeRaf);
      if (resizeTimer !== null) window.clearTimeout(resizeTimer);
      mapInstance.remove();
      setMap(null);
    };
  }, []); // Empty deps - map should only be created once!

  useEffect(() => {
    if (!map || !defaultBounds) return;
    // fitBounds expects [sw, ne] - use jumpTo for instant positioning without animation
    // Increased bottom padding to ensure lower sectors are fully visible
    const sw = [defaultBounds.west, defaultBounds.south] as [number, number];
    const ne = [defaultBounds.east, defaultBounds.north] as [number, number];
    map.fitBounds([sw, ne], {
      duration: 0,
      padding: {
        top: 50,
        bottom: 100, // Increased bottom padding to show lower sectors
        left: 50,
        right: 50
      }
    });
  }, [map, defaultBounds]);

  const value = useMemo(() => ({ map, id }), [map, id]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', ...style }}>
      <div
        ref={containerRef}
        data-testid={id ?? 'map'}
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          borderRadius: 0,
          boxSizing: 'border-box'
        }}
      />
      <MapContext.Provider value={value}>{map ? children : null}</MapContext.Provider>
      {/* Marker styles for AgentMarkerManager */}
      <style>{`.agent-marker{transition: transform 0.08s linear; will-change: transform; pointer-events: none;}`}</style>
    </div>
  );
};

export const useMap = (id: string | null = null): maplibregl.Map | null => {
  const ctx = useContext(MapContext);
  
  // If id is specified, verify it matches the context map's id
  if (id && ctx?.id !== id) {
    console.warn(`[MapLibre] useMap requested map with id "${id}" but context has id "${ctx?.id}"`);
    return null;
  }
  
  return ctx?.map ?? null;
};
