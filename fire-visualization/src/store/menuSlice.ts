// types
import { createSlice } from '@reduxjs/toolkit';

export type MenuState = {
  openItem: string[];
  defaultId: string;
  openComponent: string;
  drawerOpen: boolean;
  componentDrawerOpen: boolean;
  drawerType: 'workspace' | 'settings' | null;
};

const initialState: MenuState = {
  openItem: ['dashboard'],
  defaultId: 'dashboard',
  openComponent: 'buttons',
  drawerOpen: false,
  componentDrawerOpen: true,
  drawerType: null,
};

export const menuSlice = createSlice({
  name: 'menu',
  initialState,
  reducers: {
    openDrawer(state, action) {
      state.drawerOpen = action.payload.drawerOpen;
    },

    openComponentDrawer(state, action) {
      state.componentDrawerOpen = action.payload.componentDrawerOpen;
    },

    setDrawerType(state, action) {
      state.drawerType = action.payload.drawerType;
    },
  },
});

export const { openDrawer, openComponentDrawer, setDrawerType } = menuSlice.actions;
export default menuSlice.reducer;
