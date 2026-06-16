import { PolygonLayer } from '@deck.gl/layers';
import { Sector } from '../../model/sector';

export const useSelectedSectorLayer = (sector?: Sector) => {
  const layer = new PolygonLayer<Sector>({
    id: 'SelectedSector',
    data: sector ? [sector] : [],
    extruded: false,
    filled: false,
    stroked: true,
    getPolygon: (s) => s.contours,
    getLineColor: [255, 255, 0],
    getLineWidth: 20,
    pickable: false,
  });
  // console.debug('[useSelectedSectorLayer] creating SelectedSector layer', { hasSector: !!sector, sectorId: sector?.sectorId ?? null });
  return layer;
};

export const useTargetSectorLayer = (sector?: Sector) => {
  const layer = new PolygonLayer<Sector>({
    id: 'TargetSector',
    data: sector ? [sector] : [],
    extruded: false,
    filled: false,
    stroked: true,
    getPolygon: (s) => s.contours,
    getLineColor: [255, 0, 255], // Magenta for target
    getLineWidth: 20,
    pickable: false,
  });
  // console.debug('[useTargetSectorLayer] creating TargetSector layer', { hasSector: !!sector, sectorId: sector?.sectorId ?? null });
  return layer;
};
