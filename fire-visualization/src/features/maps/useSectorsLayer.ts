import { createElement, CSSProperties, useMemo } from 'react';
import { Configuration } from '../../model/configuration';
import { PolygonLayer, TextLayer } from '@deck.gl/layers';
import { Sector } from '../../model/sector';
import { PickingInfo } from '@deck.gl/core';
import { eventEmitter } from '@shared/utils/eventEmitter';
import { Box, List, ListItem, ListItemText } from '@mui/material';

const styles = {
  tooltip: {
    display: 'block',
    zIndex: 1,
    position: 'absolute',
    backgroundColor: 'rgba(66, 66, 66, 0.6)',
    color: 'white',
    padding: '5px',
    borderRadius: '5px',
  } as const,
} satisfies Record<string, CSSProperties>;

let _lastHover = { sectorId: null as number | null, ts: 0 };
const HOVER_THROTTLE_MS = 0;

// When a sector's burnLevel rises above this threshold, it is considered "lost"
// and rendered with a distinctive dark grey border (standardized from theme grey[600]).
// NOTE: burnLevel comes from the simulation; current runs keep it in a low range
// (e.g. 0–5), but the product definition expects a percentage-like scale where
// values above ~78 should be treated as fully burned.
const LOST_BURN_LEVEL_THRESHOLD = 78;
const HIDE_LABELS_SECTOR_COUNT = 120;

export const useSectorsLayer = ({ sectors }: Configuration, disableOnHover?: boolean, onClickHandler?: (sectorId: number) => void, currentSectorId?: number | null) => {
  // OPTIMIZATION: Create update triggers for Deck.gl to avoid unnecessary re-renders
  // Only re-render when actual sector data (fireLevel, burnLevel, extinguishLevel) changes
  const sectorColorTriggers = useMemo(() => {
    return sectors.map(s => [s.sectorId, s.fireLevel, s.burnLevel, s.extinguishLevel, s.threatLevel]);
  }, [sectors]);

  return useMemo(() => {
    // 1. The Polygon Layer (The shapes)
    const polygonLayer = new PolygonLayer<Sector>({
      id: 'PolygonLayer',
      data: sectors,
      extruded: false,
      filled: true,
      stroked: true,
      getPolygon: (sector) => sector.contours,
      // OPTIMIZATION: Use updateTriggers to only update when visual properties change
      updateTriggers: {
        getFillColor: sectorColorTriggers,
        getLineColor: sectorColorTriggers,
        getLineWidth: sectorColorTriggers,
      },
      getFillColor: (sector) => {
        const isLost = sector.burnLevel !== null && sector.burnLevel > LOST_BURN_LEVEL_THRESHOLD;

        // Sektor ugaszony przez brygadę: ogień zgaszony i wysoki poziom gaszenia.
        // Sprawdzamy to PRZED "spalony", bo sektor uratowany późno też ma wysoki
        // burnLevel, a chcemy go pokazać na niebiesko (straż wygrała), nie czarno.
        if ((sector.fireLevel === null || sector.fireLevel === 0)
            && sector.extinguishLevel !== null && sector.extinguishLevel >= 50) {
          return [40, 110, 220, 150];
        }

        // Sektor spalony (burnLevel powyżej progu) — ciemny, wyraźnie inny
        // niż aktywnie płonący.
        if (isLost) {
          return [30, 30, 30, 200];
        }

        // Aktywny pożar — kolor zależny od stopnia (1-4), skala fireLevel 0-100
        // wg klasyfikacji silnika: (0,25] EARLY, (25,50] MEDIUM, (50,75] FULL,
        // (75,100] EXTREME. Im wyższy stopień, tym cieplejszy i mocniejszy kolor.
        if (sector.fireLevel !== null && sector.fireLevel > 0) {
          const lvl = sector.fireLevel;
          if (lvl <= 25) return [255, 214, 10, 120];   // 1 EARLY — żółty
          if (lvl <= 50) return [255, 140, 0, 150];    // 2 MEDIUM — pomarańczowy
          if (lvl <= 75) return [240, 60, 0, 180];     // 3 FULL — czerwono-pomarańczowy
          return [150, 0, 0, 210];                      // 4 EXTREME — ciemnoczerwony
        }

        // Zagrożenie sektorów bez ognia pokazujemy obwódką (getLineColor),
        // nie wypełnieniem, żeby nie myliło się z aktywnym pożarem.

        // Fallback or additional indicators (like temperature or PM2.5)
        let intensityLevel = 0;
        const temp = sector.initialState.temperature;
        const pm25 = sector.initialState.pm2_5Concentration;

        if (temp > 55 || pm25 > 250) intensityLevel = 3;
        else if (temp > 45 || pm25 > 100) intensityLevel = 2;
        else if (temp > 35 || pm25 > 50) intensityLevel = 1;

        if (intensityLevel === 3) return [200, 0, 0, 40];
        if (intensityLevel === 2) return [255, 140, 0, 30];
        if (intensityLevel === 1) return [255, 200, 0, 20];

        // Base color to make all sectors always visible as requested - extremely faint
        return [255, 255, 255, 10];
      },
      getLineColor: (sector) => {
        const isLost = sector.burnLevel !== null && sector.burnLevel > LOST_BURN_LEVEL_THRESHOLD;
        // Scale opacity based on sector count - more sectors = less visible borders
        const sectorCount = sectors?.length || 1;
        const opacity = sectorCount > 100 ? 80 : sectorCount > 50 ? 120 : sectorCount > 25 ? 150 : 200;

        // Sektor spalony: standardowa szara ramka.
        if (isLost) return [89, 89, 89, Math.min(255, opacity + 55)];

        // Sektor płonący: ciepła ramka, wypełnienie i tak pokazuje ogień.
        if (sector.fireLevel !== null && sector.fireLevel > 0) {
          return [255, 60, 0, opacity];
        }

        // Sektor bez ognia: poziom zagrożenia kodujemy obwódką w palecie
        // lawenda -> fiolet -> magenta -> róż. To inna rodzina barw niż pożar,
        // a poziomy wyraźnie różnią się odcieniem, nie tylko jasnością.
        switch (sector.threatLevel) {
          case 'MEDIUM':    return [180, 160, 255, 200];  // jasny lawendowy
          case 'HIGH':      return [165, 85, 240, 230];   // fiolet
          case 'VERY_HIGH': return [220, 50, 220, 245];   // magenta
          case 'CRITICAL':  return [255, 20, 130, 255];   // różowo-magenta
        }
        // LOW albo brak danych: ledwo widoczna neutralna ramka
        return [120, 120, 130, Math.max(20, opacity - 120)];
      },
      getLineWidth: (sector) => {
        const sectorCount = sectors?.length || 1;
        // Bazowa grubość zależna od liczby sektorów (gęściej = cieniej).
        const base = sectorCount > 100 ? 1 : sectorCount > 50 ? 1.5 : sectorCount > 25 ? 2 : 3;

        // Sektor bez ognia: im wyższe zagrożenie, tym grubsza fioletowa ramka.
        if (sector.fireLevel === null || sector.fireLevel === 0) {
          switch (sector.threatLevel) {
            case 'MEDIUM':    return Math.max(base, 2);
            case 'HIGH':      return Math.max(base, 3);
            case 'VERY_HIGH': return Math.max(base, 4);
            case 'CRITICAL':  return Math.max(base, 5);
          }
        }
        return base;
      },
      // Grubość w pikselach, żeby fioletowe ramki zagrożenia były czytelne
      // niezależnie od poziomu przybliżenia.
      lineWidthUnits: 'pixels',
      lineWidthMinPixels: 1,
      highlightColor: [255, 80, 0, 80], // Reduced opacity from 220 to 80 for subtler hover effect
      autoHighlight: !disableOnHover,
      pickable: true,
      onHover: (pickingInfo: PickingInfo<Sector>) => {
        if (disableOnHover) {
          eventEmitter.emit('onTooltipChange', null);
          return;
        }
        const now = Date.now();
        const sectorId = pickingInfo?.object?.sectorId ?? null;
        if (sectorId === _lastHover.sectorId && now - _lastHover.ts < HOVER_THROTTLE_MS) return;
        _lastHover = { sectorId, ts: now };

        const { x, y, object: sector, viewport } = pickingInfo;
        if (!sector) {
          eventEmitter.emit('onTooltipChange', null);
          return;
        }

        const sectorCenterCoords = {
          longitude: sector.contours.reduce((sum, p) => sum + p[0], 0) / sector.contours.length,
          latitude: sector.contours.reduce((sum, p) => sum + p[1], 0) / sector.contours.length,
        };
        const sectorCenterPixels = viewport?.project([sectorCenterCoords.longitude, sectorCenterCoords.latitude]);

        const tooltip = createElement(
          Box,
          {
            id: `tooltip-sector`,
            className: `sector-${sector.sectorId}`,
            sx: {
              ...styles.tooltip,
              left: Math.round(sectorCenterPixels?.[0] ?? x) + 'px',
              // Move the tooltip up by 40px to avoid overlap with bottom edges
              top: (Math.round(sectorCenterPixels?.[1] ?? y) - 40) + 'px',
              transform: 'translate(-50%, -100%)', // Center horizontally and place above the point
            },
          },
          createElement(
            List,
            { dense: false },
            Configuration.sectors
              .toString(sector)
              .split('\n')
              .map((str, i) => createElement(ListItem, { sx: { py: 0 }, key: i }, createElement(ListItemText, { primary: str })))
          ),
        );
        eventEmitter.emit('onTooltipChange', tooltip);
      },
      onClick: (pickingInfo: PickingInfo<Sector>) => {
        const { object: sector } = pickingInfo;
        if (onClickHandler && sector) {
          onClickHandler(sector.sectorId);
        }
        if (disableOnHover) return;
        // Don't emit sector change if clicking the same sector that's already selected
        // This prevents exiting edit mode when double-clicking or multi-clicking the selected sector
        if (sector && currentSectorId !== null && sector.sectorId === currentSectorId) {
          return;
        }
        eventEmitter.emit('onSectorChange', sector?.sectorId ?? null);
      },
      // Transitions for smooth fire visualization - longer duration for even better performance
      transitions: {
        getFillColor: 500, // Responsive color transitions
        getLineColor: 500,
      }
    });

    // 2. The Text Layer (The labels)
    const sectorCount = sectors?.length || 0;
    const textLayer = new TextLayer({
      id: 'sector-text-layer',
      data: sectorCount > HIDE_LABELS_SECTOR_COUNT ? [] : sectors.map((sector) => {
        if (sector.sectorId === 1 || sector.sectorId === sectors.length) {
        }
        // Find the bottom-right corner (max longitude, min latitude)
        const lons = sector.contours.map(p => p[0]);
        const lats = sector.contours.map(p => p[1]);
        const maxLng = Math.max(...lons);
        const minLat = Math.min(...lats);

        return {
          position: [maxLng, minLat],
          text: `Sector_${sector.sectorId.toString().padStart(2, '0')} [R${sector.row},C${sector.column}]`,
        };
      }),
      getPosition: (d: any) => d.position,
      getText: (d: any) => d.text,
      // Scale font size based on sector count - more sectors = smaller labels
      getSize: sectorCount > 100 ? 6 : sectorCount > 50 ? 7 : sectorCount > 25 ? 8 : 9,
      sizeUnits: 'pixels',
      // Scale opacity based on sector count - more sectors = less visible labels
      getColor: (d: any) => {
        const opacity = sectorCount > 100 ? 120 : sectorCount > 50 ? 150 : sectorCount > 25 ? 180 : 220;
        return [255, 255, 255, opacity];
      },
      getTextAnchor: 'end', // Align to right
      getAlignmentBaseline: 'bottom', // Align to bottom
      getPixelOffset: [-5, -5], // Small margin from the corner
      background: true,
      // Scale background opacity based on sector count
      getBackgroundColor: (d: any) => {
        const opacity = sectorCount > 100 ? 80 : sectorCount > 50 ? 100 : sectorCount > 25 ? 120 : 140;
        return [0, 0, 0, opacity];
      },
      fontFamily: 'Monaco, monospace',
      fontWeight: 'bold',
      billboard: true,
    });

    // console.debug('[useSectorsLayer] creating sector layers', { sectorCount, includeLabels: sectorCount <= HIDE_LABELS_SECTOR_COUNT });
    return sectorCount > HIDE_LABELS_SECTOR_COUNT ? [polygonLayer] : [polygonLayer, textLayer];
  }, [sectors, disableOnHover, onClickHandler, currentSectorId, sectorColorTriggers]);
};
