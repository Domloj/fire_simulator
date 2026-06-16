import { PolygonLayer } from '@deck.gl/layers';
import { Region } from '../../model/geography';
import { Configuration } from '../../model/configuration';
import { useMemo } from 'react';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';

export const useForestBorderLayer = ({ location }: Configuration) => {
  // Forest border removed - return empty layer to not render the green border
  return useMemo(
    () => {
      // console.debug('[useForestBorderLayer] creating ForestBorder layer (no data)', { location });
      return new PolygonLayer<Region>({
        id: 'ForestBorder',
        data: [],
        extruded: false,
        filled: false,
        stroked: true,
        pickable: false,
      });
    },
    [location],
  );
};
