import { useEffect, useState, useCallback } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useTheme, useMediaQuery } from '@mui/material';
import { RootState } from '../../store/reduxStore';
import { openDrawer } from '../../store/menuSlice';

export const useDrawerState = () => {
  const theme = useTheme();
  const matchDownLG = useMediaQuery(theme.breakpoints.down('lg'));
  const dispatch = useDispatch();
  const { drawerOpen } = useSelector((state: RootState) => state.menu);

  const [open, setOpen] = useState(drawerOpen);

  const handleDrawerToggle = useCallback(() => {
    setOpen((prev) => {
      const newValue = !prev;
      dispatch(openDrawer({ drawerOpen: newValue }));
      return newValue;
    });
  }, [dispatch]);

  // Sync drawer state with media query
  useEffect(() => {
    const shouldBeOpen = !matchDownLG;
    setOpen(shouldBeOpen);
    dispatch(openDrawer({ drawerOpen: shouldBeOpen }));
  }, [matchDownLG, dispatch]);

  // Sync local state with Redux state
  useEffect(() => {
    if (open !== drawerOpen) {
      setOpen(drawerOpen);
    }
  }, [drawerOpen, open]);

  return {
    open,
    handleDrawerToggle,
  };
};
