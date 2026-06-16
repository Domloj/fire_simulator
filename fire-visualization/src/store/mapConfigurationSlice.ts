import { createSlice } from '@reduxjs/toolkit';
import { Configuration, ConfigurationUpdate, getDefaultConfiguration } from '../model/configuration';
import { FileSystemNode } from '../model/FileSystemNode';
import { NodeTypeEnum } from '../model/NodeTypeEnum';
import { Sensor } from '../model/sensor';
import { Camera } from '../model/camera';
import { FireBrigade } from '../model/FireBrigade';
import { ForesterPatrol } from '../model/ForesterPatrol';
// import { performanceMonitor } from '../shared/utils/performanceMonitor';

// Performance monitoring
let _updateSectorStatesCount = 0;
let _updateSectorAndAgentStatesCount = 0;
let _lastUpdateTime = Date.now();

type mapConfigurationState = {
  fileSystemNode: FileSystemNode;
  configuration: Configuration;
  currentSectorId: number | null;
};

const initialState: mapConfigurationState = {
  fileSystemNode: {
    id: '',
    name: '',
    nodeType: NodeTypeEnum.FILE,
  },
  configuration: getDefaultConfiguration(),
  currentSectorId: null,
};

export const mapConfigurationSlice = createSlice({
  name: 'mapConfiguration',
  initialState,
  reducers: {

    setConfiguration: (state, action) => {
      const { configuration } = action.payload;
      const processedSectors = Configuration.preprocessSectors(configuration);
      state.configuration = { ...configuration, sectors: processedSectors };
    },

    updateConfiguration: (state, action: { payload: { configurationUpdate: ConfigurationUpdate }; type: string }) => {
      const { configurationUpdate } = action.payload;
      state.configuration = Configuration.updateConfiguration(state.configuration, configurationUpdate);
    },

    updateSectorStatesFast: (state, action) => {
      const startTime = performance.now();
      const { sectorUpdates } = action.payload;
      if (!sectorUpdates || sectorUpdates.length === 0) {
        return;
      }

      const sectorById = new Map(state.configuration.sectors.map((sector) => [sector.sectorId, sector]));
      for (const update of sectorUpdates) {
        const sector = sectorById.get(update.sectorId);
        if (!sector) {
          continue;
        }

        sector.fireLevel = update.fireLevel;
        sector.burnLevel = update.burnLevel;
        sector.extinguishLevel = update.extinguishLevel;
        sector.fireState = update.fireState ?? sector.fireState;
        sector.threatLevel = update.threatLevel ?? sector.threatLevel;
        sector.initialState.fireLevel = update.fireLevel;
        sector.initialState.burnLevel = update.burnLevel;
        sector.initialState.extinguishLevel = update.extinguishLevel;
      }
      
    },
    updateSectorAndAgentStatesFast: (state, action) => {
      const startTime = performance.now();
      const { sectorUpdates, agentUpdates } = action.payload;
      
      let sectorsUpdated = 0;
      let fireBrigadesUpdated = 0;
      let foresterPatrolsUpdated = 0;
      
      if (sectorUpdates && sectorUpdates.length > 0) {
        const sectorById = new Map(state.configuration.sectors.map((sector) => [sector.sectorId, sector]));
        for (const update of sectorUpdates) {
          const sector = sectorById.get(update.sectorId);
          if (!sector) {
            continue;
          }
          sector.fireLevel = update.fireLevel;
          sector.burnLevel = update.burnLevel;
          sector.extinguishLevel = update.extinguishLevel;
          sector.fireState = update.fireState ?? sector.fireState;
          sector.threatLevel = update.threatLevel ?? sector.threatLevel;
          sector.initialState.fireLevel = update.fireLevel;
          sector.initialState.burnLevel = update.burnLevel;
          sector.initialState.extinguishLevel = update.extinguishLevel;
          sectorsUpdated++;
        }
      }
      
      if (agentUpdates) {
        if (agentUpdates.fireBrigades && agentUpdates.fireBrigades.length > 0) {
          const fbMap = new Map(state.configuration.fireBrigades.map(fb => [fb.fireBrigadeId, fb]));
          for (const update of agentUpdates.fireBrigades) {
            const fb = fbMap.get(update.fireBrigadeId);
            if (fb && update.location) {
              fb.currentLocation = update.location;
              fb.sectorId = update.sectorId ?? fb.sectorId;
              fb.state = update.state ?? fb.state;
              fb.timestamp = Date.now();
              fireBrigadesUpdated++;
            }
          }
        }
        
        if (agentUpdates.foresterPatrols && agentUpdates.foresterPatrols.length > 0) {
          const fpMap = new Map(state.configuration.foresterPatrols.map(fp => [fp.foresterPatrolId, fp]));
          for (const update of agentUpdates.foresterPatrols) {
            const fp = fpMap.get(update.foresterPatrolId);
            if (fp && update.location) {
              fp.currentLocation = update.location;
              fp.sectorId = update.sectorId ?? fp.sectorId;
              fp.state = update.state ?? fp.state;
              fp.timestamp = Date.now();
              foresterPatrolsUpdated++;
            }
          }
        }
      }
      
    },
    setCurrentSectorId: (state, action) => {
      const { currentSectorId: prevSectorId } = state;
      const { currentSectorId: nextSectorId } = action.payload;
      state.currentSectorId = prevSectorId !== nextSectorId ? nextSectorId : null;
    },
    setFileSystemNode: (state, action) => {
      const { fileSystemNode } = action.payload;
      state.fileSystemNode = fileSystemNode;
    },
    addSensor: (state, action: { payload: { sensor: Sensor }; type: string }) => {
      const { sensor } = action.payload;
      state.configuration.sensors.push(sensor);
    },
    addCamera: (state, action: { payload: { camera: Camera }; type: string }) => {
      const { camera } = action.payload;
      state.configuration.cameras.push(camera);
    },
    addFireBrigade: (state, action: { payload: { fireBrigade: FireBrigade }; type: string }) => {
      const { fireBrigade } = action.payload;
      state.configuration.fireBrigades.push(fireBrigade);
    },
    addForesterPatrol: (state, action: { payload: { foresterPatrol: ForesterPatrol }; type: string }) => {
      const { foresterPatrol } = action.payload;
      state.configuration.foresterPatrols.push(foresterPatrol);
    },
  },
});

export const {
  setConfiguration,
  updateConfiguration,
  updateSectorStatesFast,
  updateSectorAndAgentStatesFast,
  setCurrentSectorId,
  setFileSystemNode,
  addSensor,
  addCamera,
  addFireBrigade,
  addForesterPatrol,
} = mapConfigurationSlice.actions;
export const { reducer: mapConfigurationReducer } = mapConfigurationSlice;
