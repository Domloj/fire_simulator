import { useEffect, useState, useRef, memo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useMap } from './MapLibre';
import DeckGL from '@deck.gl/react';
import type { LayersList } from '@deck.gl/core';

export type DeckglOverlayProps = {
  layers?: LayersList;
  overlayId?: string;
  capturePointerEvents?: boolean;
};

/**
 * DeckGL overlay for MapLibre - renders deck.gl layers on top of the map
 * OPTIMIZATION: Memoized to prevent unnecessary re-renders
 * CRITICAL: Handles WebGL context loss prevention
 */
const DeckGlOverlayComponent = ({ layers, overlayId = 'default', capturePointerEvents = false }: DeckglOverlayProps) => {
  const map: any = useMap();
  const [overlayContainer, setOverlayContainer] = useState<HTMLDivElement | null>(null);
  const [viewState, setViewState] = useState<any>(null);
  const renderCountRef = useRef(0);
  const lastRenderTimeRef = useRef(Date.now());
  const viewStateUpdateCountRef = useRef(0);
  const deckRef = useRef<any>(null);

  useEffect(() => {
    if (layers && layers.length > 0) {
      // logging removed for performance
    }
  }, [layers, overlayId]);

  const onWebGLInitialized = useCallback((gl: WebGLRenderingContext) => {
    // logging removed for performance
    const canvas = gl.canvas as HTMLCanvasElement;

    canvas.addEventListener('webglcontextlost', (e: Event) => {
      console.error(`[DeckGL-${overlayId}] WebGL context lost! Preventing default...`);
      e.preventDefault();
    });

    canvas.addEventListener('webglcontextrestored', () => {
      // logging removed for performance
    });
  }, [overlayId]);

  useEffect(() => {
    if (!map) return;

    const mapContainer = map.getContainer?.() || map.getDiv?.();
    if (!mapContainer) {
      return;
    }

    const overlayClassName = `deck-overlay-${overlayId}`;
    let overlayDiv = mapContainer.querySelector(`.${overlayClassName}`) as HTMLDivElement;
    if (!overlayDiv) {
      overlayDiv = document.createElement('div');
      overlayDiv.className = overlayClassName;
      overlayDiv.style.position = 'absolute';
      overlayDiv.style.top = '0';
      overlayDiv.style.left = '0';
      overlayDiv.style.width = '100%';
      overlayDiv.style.height = '100%';
      overlayDiv.style.zIndex = overlayId === 'drawing' ? '2' : '1';
      mapContainer.appendChild(overlayDiv);
    }

    setOverlayContainer(overlayDiv);
    let lastViewStateUpdate = 0;
    const VIEW_STATE_THROTTLE_MS = 50;

    const updateViewState = () => {
      if (!map) return;

      const now = Date.now();
      if (now - lastViewStateUpdate < VIEW_STATE_THROTTLE_MS) {
        return; 
      }

      viewStateUpdateCountRef.current++;

      lastViewStateUpdate = now;

      try {
        const center = map.getCenter();
        const zoom = map.getZoom();
        const bearing = map.getBearing?.() ?? 0;

        setViewState({
          longitude: center.lng,
          latitude: center.lat,
          zoom: zoom,
          bearing: bearing,
          pitch: 0
        });
      } catch (err) {
        // ignore errors
      }
    };

    updateViewState();
    map.on('move', updateViewState);
    map.on('moveend', updateViewState);
    map.on('zoom', updateViewState);
    map.on('zoomend', updateViewState);

    return () => {
      map.off('move', updateViewState);
      map.off('moveend', updateViewState);
      map.off('zoom', updateViewState);
      map.off('zoomend', updateViewState);
    };
  }, [map, overlayId]);

  useEffect(() => {
    if (!overlayContainer) {
      return;
    }

    const pointerEventsValue = capturePointerEvents ? 'auto' : 'none';
    overlayContainer.style.pointerEvents = pointerEventsValue;

    const updateCanvasPointerEvents = () => {
      const canvas = overlayContainer.querySelector('canvas');
      if (canvas) {
        canvas.style.pointerEvents = pointerEventsValue;
      }
    };

    updateCanvasPointerEvents();

    const observer = new MutationObserver(() => {
      updateCanvasPointerEvents();
    });

    observer.observe(overlayContainer, {
      childList: true,
      subtree: true,
    });


    let mouseDownHandler: ((e: MouseEvent) => void) | null = null;
    if (overlayId === 'drawing') {
      mouseDownHandler = (e: MouseEvent) => {
        const canvas = overlayContainer.querySelector('canvas');
        if (canvas) {
          // ignore
        }
      };
      overlayContainer.addEventListener('mousedown', mouseDownHandler, true);
    }

    return () => {
      observer.disconnect();
      if (mouseDownHandler) {
        overlayContainer.removeEventListener('mousedown', mouseDownHandler, true);
      }
    };
  }, [overlayContainer, capturePointerEvents, overlayId]);

  if (!overlayContainer || !viewState) {
    return null;
  }

  renderCountRef.current++;
  const now = Date.now();
  lastRenderTimeRef.current = now;

  return createPortal(
    <DeckGL
      ref={deckRef}
      viewState={viewState}
      controller={false}
      layers={layers || []}
      style={{ pointerEvents: capturePointerEvents ? 'auto' : 'none' }}
      getCursor={() => 'inherit'}
      onWebGLInitialized={onWebGLInitialized}
      _animate={false}
    />,
    overlayContainer
  );
};

export const DeckGlOverlay = memo(DeckGlOverlayComponent, (prevProps, nextProps) => {
  return (
    prevProps.layers === nextProps.layers &&
    prevProps.overlayId === nextProps.overlayId &&
    prevProps.capturePointerEvents === nextProps.capturePointerEvents
  );
});