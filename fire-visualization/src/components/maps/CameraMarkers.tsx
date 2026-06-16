import { useRef, useEffect } from 'react';

// maps
import { useMap, AdvancedMarker } from '@vis.gl/react-google-maps';
import { MarkerClusterer } from '@googlemaps/markerclusterer';
import type { Marker } from '@googlemaps/markerclusterer';

import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { Camera } from '../../model/camera';

export type CameraMarker = {
  location: google.maps.LatLngLiteral;
  key: string;
};

export const CameraMarkers = () => {
  const map = useMap('main-map');

  const markers = useRef<{ [key: string]: Marker }>({});
  const clusterer = useRef<MarkerClusterer | null>(null);
  const cameras = useSelector((state: RootState) => state.mapConfiguration.configuration?.cameras || []);

  useEffect(() => {
    if (!map) return;
    if (!clusterer.current) {
      clusterer.current = new MarkerClusterer({ map });
    }
  }, [map]);

  useEffect(() => {
    clusterer.current?.clearMarkers();
    clusterer.current?.addMarkers(Object.values(markers.current));
  }, [markers]);

  const setMarkerRef = (marker: Marker | null, key: string) => {
    if (marker && markers.current[key]) return;
    if (!marker && !markers.current[key]) return;

    if (marker) {
      markers.current[key] = marker;
    } else {
      delete markers.current[key];
    }
  };

  return (
    <>
      {cameras.map((camera) => {
        const { location, key } = Camera.toMarkerProps(camera);
        return (
          <AdvancedMarker
            position={location}
            key={key}
            ref={(marker: Marker | null) => setMarkerRef(marker, key)}
          >
            <span className="camera-marker">📹</span>
          </AdvancedMarker>
        );
      })}
    </>
  );
};
