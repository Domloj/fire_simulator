import { combineReducers } from 'redux';
import menuReducer from './menuSlice';
import { mapConfigurationReducer } from './mapConfigurationSlice';
import { serverCommunicationReducer } from './serverCommunicationReducers';
import recommendationReducer from './recommendationSlice';
import { logsReducer } from './logsSlice';
import { settingsReducer } from './settingsSlice';

export const combinedReducers = combineReducers({ 
    menu: menuReducer, 
    mapConfiguration: mapConfigurationReducer, 
    serverCommunication: serverCommunicationReducer,
    recommendation: recommendationReducer,
    logs: logsReducer,
    settings: settingsReducer,
});
