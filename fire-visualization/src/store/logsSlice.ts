import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type LogEntry = {
  id: string;
  timestamp: string;
  text: string;
  level?: 'info' | 'warn' | 'error';
  source?: 'simulation' | 'llm' | 'ui';
};

type LogsState = {
  logs: LogEntry[];
  llmLogs: LogEntry[];
  maxEntries: number;
};

const MAX_ENTRIES_DEFAULT = 200;

const initialState: LogsState = {
  logs: [],
  llmLogs: [],
  maxEntries: MAX_ENTRIES_DEFAULT,
};

const createLogEntry = (payload: Omit<LogEntry, 'id' | 'timestamp'>): LogEntry => ({
  id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2),
  timestamp: new Date().toISOString(),
  ...payload,
});

const trim = (arr: LogEntry[], maxEntries: number): LogEntry[] =>
  arr.length > maxEntries ? arr.slice(arr.length - maxEntries) : arr;

const addLogToArray = (
  state: LogsState,
  logArray: 'logs' | 'llmLogs',
  payload: Omit<LogEntry, 'id' | 'timestamp'>
) => {
  const entry = createLogEntry(payload);
  state[logArray].push(entry);
  state[logArray] = trim(state[logArray], state.maxEntries);
};

export const logsSlice = createSlice({
  name: 'logs',
  initialState,
  reducers: {
    addLog(state, action: PayloadAction<Omit<LogEntry, 'id' | 'timestamp'>>) {
      addLogToArray(state, 'logs', action.payload);
    },
    addLlmLog(state, action: PayloadAction<Omit<LogEntry, 'id' | 'timestamp'>>) {
      addLogToArray(state, 'llmLogs', action.payload);
    },
    clearLogs(state) {
      state.logs = [];
    },
    clearLlmLogs(state) {
      state.llmLogs = [];
    },
    setMaxEntries(state, action: PayloadAction<number>) {
      state.maxEntries = action.payload;
      state.logs = trim(state.logs, state.maxEntries);
      state.llmLogs = trim(state.llmLogs, state.maxEntries);
    },
  },
});

export const { addLog, addLlmLog, clearLogs, clearLlmLogs, setMaxEntries } = logsSlice.actions;
export const { reducer: logsReducer } = logsSlice;
