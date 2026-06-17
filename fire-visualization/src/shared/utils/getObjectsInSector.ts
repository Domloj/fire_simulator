import { Sector } from '../../model/sector';
import { isPointInBounds } from './isPointInBounds';

// Generic helper: filter objects that have either `location` or `currentLocation` with { latitude, longitude }
export const getObjectsInSector = <T extends { location?: { latitude: number; longitude: number }; currentLocation?: { latitude: number; longitude: number } }>(
   sector: Sector,
   objects: T[] = [],
): T[] => {
   if (!sector || !sector.contours || sector.contours.length === 0) return [];

   const sectorBounds = Sector.getBoundsFromContours(sector);

   return objects.filter((obj) => {
      if (!obj) return false;
      const loc = (obj as any).location ?? (obj as any).currentLocation;
      if (!loc || typeof loc.latitude !== 'number' || typeof loc.longitude !== 'number') return false;
      return isPointInBounds(loc, sectorBounds as any);
   });
};

export default getObjectsInSector;