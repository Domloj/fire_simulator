import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface SettingsState {
  activeSettingId: string | null;
}

const initialState: SettingsState = {
  activeSettingId: null,
};

export const settingsSlice = createSlice({
  name: 'settings',
  initialState,
  reducers: {
    setActiveSettingId: (state, action: PayloadAction<string | null>) => {
      state.activeSettingId = action.payload;
    },
  },
});

export const { setActiveSettingId } = settingsSlice.actions;
export const settingsReducer = settingsSlice.reducer;
