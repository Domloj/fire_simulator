import { useMap } from '../../components/maps/MapLibre';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import DeckGL from '@deck.gl/react';
import type { LayersList } from '@deck.gl/core';

export type DeckglOverlayProps = { layers?: LayersList };

/**
 * Renders deck.gl layers over MapLibre map
 */
export const DeckGlOverlay = ({ layers }: DeckglOverlayProps) => {
  const map = useMap();
  const [overlayContainer, setOverlayContainer] = useState<HTMLDivElement | null>(null);
  const [viewState, setViewState] = useState<{ longitude: number; latitude: number; zoom: number; pitch: number; bearing: number } | null>(null);

  useEffect(() => {
    if (!map) { return; }

    const mapContainer = (map as any).getContainer?.() || (map as any).getDiv?.();
    if (!mapContainer) { return; }

    const overlayDiv = document.createElement('div');

    overlayDiv.style.position = 'absolute';
    overlayDiv.style.top = '0';
    overlayDiv.style.left = '0';
    overlayDiv.style.width = '100%';
    overlayDiv.style.height = '100%';
    overlayDiv.style.pointerEvents = 'none';

    mapContainer.appendChild(overlayDiv);
    setOverlayContainer(overlayDiv);

    const updateViewState = () => {
      const center = map.getCenter();
      const zoom = map.getZoom();

      setViewState({
        longitude: center.lng,
        latitude: center.lat,
        zoom: zoom,
        pitch: 0,
        bearing: 0
      });
    };

    updateViewState();
    map.on('move', updateViewState);

    return () => {
      map.off('move', updateViewState);
      if (overlayDiv.parentNode) {
        overlayDiv.parentNode.removeChild(overlayDiv);
      }
    };
  }, [map]);

  useEffect(() => {
    console.debug('[DeckGlOverlay] layers changed', (layers || []).map((l: unknown) => (l as any).id));
  }, [layers]);

  if (!overlayContainer || !viewState) return null;

  return createPortal(
    <DeckGL
      viewState={viewState}
      controller={false}
      layers={layers || []}
      style={{ pointerEvents: 'auto' }}
      onAfterRender={() => {
        try {
          console.debug('[DeckGlOverlay] onAfterRender', { layers: (layers || []).map((l: unknown) => (l as any).id), viewState });
        } catch (e) {
          // ignore logging errors
        }
      }}
    />,
    overlayContainer
  );
};
