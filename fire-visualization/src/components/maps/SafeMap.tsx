import { Map } from './MapLibre';
import { getDefaultMapLocation } from '../../model/common';

/**
 * SafeMap wraps MapLibre <Map> and ensures initialCenter/initialZoom are present.
 */
export const SafeMap = (props: any) => {
  const defaultLoc = getDefaultMapLocation();
  const initialCenter = props.initialCenter ?? [defaultLoc.longitude, defaultLoc.latitude];
  const initialZoom = props.initialZoom ?? 5;

  return <Map {...props} initialCenter={initialCenter} initialZoom={initialZoom} />;
};

export default SafeMap;