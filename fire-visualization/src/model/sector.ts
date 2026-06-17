import type { Direction } from './geography';

export const SectorTypes = ['DECIDUOUS', 'MIXED', 'CONIFEROUS', 'FIELD', 'FALLOW', 'WATER', 'UNTRACKED'] as const;

type SectorType = (typeof SectorTypes)[number];

export interface Sector {
  sectorId: number;
  row: number;                    // row number in the map
  column: number;                 // column number in the map
  sectorType: SectorType;
  initialState: SectorState;
  contours: [number, number][];
  fireLevel: number | null;       // level of fire in this sector
  burnLevel: number | null;       // level of burn in this sector
  extinguishLevel: number | null; // level of extinguishment of the fire in this sector
  fireState?: string | null;      // FireState z silnika (NON_COMBUSTED..SEVERE/COMBUSTED)
  threatLevel?: string | null;    // poziom zagrożenia (LOW..CRITICAL), monitoring leśników
  assignedBrigades?: number[];    // IDs of fire brigades assigned to this sector
}

export type SectorUpdate = {
  sectorId: number;
  state: SectorStateUpdate;
  contours: [number, number][];   // [longitude, latitude] of the contours of the sector
  assignedBrigades?: number[];
}

// TODO adjust this type
type SectorStateUpdate = {
  temperature: number;
  windSpeed: number;
  windDirection: Direction;
  airHumidity: number;
  plantLitterMoisture: number;
  co2Concentration: number;
  pm2_5Concentration: number;
  timestamp: number | null;      // timestamp of the update
  fireLevel: number | null;
  burnLevel: number | null;
  extinguishLevel: number | null;
  fireState?: string | null;
  threatLevel?: string | null;
}

interface SectorState {
  temperature: number;
  windSpeed: number;
  windDirection: Direction;
  airHumidity: number;
  plantLitterMoisture: number;
  co2Concentration: number;
  pm2_5Concentration: number;
  fireLevel: number | null;
  burnLevel: number | null;
  extinguishLevel: number | null;
}

export const Sector = {
  getBoundsFromContours: ({ contours }: Sector): google.maps.LatLngBoundsLiteral => {
    return contours.reduce(
      (acc: google.maps.LatLngBoundsLiteral, [longitude, latitude]) => {
        if (longitude < acc.east) acc.east = longitude;
        if (latitude > acc.north) acc.north = latitude;
        if (latitude < acc.south) acc.south = latitude;
        if (longitude > acc.west) acc.west = longitude;
        return acc;
      },
      {
        east: Infinity,
        north: -Infinity,
        south: Infinity,
        west: -Infinity,
      },
    );
  },
  updateSector: (sector: Sector, sectorUpdate: SectorUpdate): Sector => {
    const { state, contours: _, assignedBrigades } = sectorUpdate;
    return {
      ...sector,
      initialState: {
        ...sector.initialState,
        ...state,
      },
      fireLevel: state.fireLevel ?? sector.fireLevel,
      burnLevel: state.burnLevel ?? sector.burnLevel,
      extinguishLevel: state.extinguishLevel ?? sector.extinguishLevel,
      fireState: state.fireState ?? sector.fireState,
      threatLevel: state.threatLevel ?? sector.threatLevel,
      assignedBrigades: assignedBrigades ?? sector.assignedBrigades,
    };
  },
};

export const getDefaultSector = (): Sector => {
  return {
    sectorId: 1,
    row: 1,
    column: 1,
    sectorType: 'DECIDUOUS',
    initialState: {
      temperature: 28,
      windSpeed: 85,
      windDirection: 'NE',
      airHumidity: 75,
      plantLitterMoisture: 26,
      co2Concentration: 18,
      pm2_5Concentration: 14,
      fireLevel: 0,
      burnLevel: 0, 
      extinguishLevel: 0
    },
    contours: [],
    assignedBrigades: [],
  };
};
