import { styled } from '@mui/material/styles';
import Drawer from '@mui/material/Drawer';

export const MiniDrawerStyled = styled(Drawer, { shouldForwardProp: (prop) => prop !== 'open' })<{ open?: boolean }>(({
  theme,
  open,
}) => {
  const openedMixin = {
    width: 215,
    borderRight: `1px solid ${theme.palette.divider}`,
    transition: theme.transitions.create(['width', 'borderRight'], {
      easing: theme.transitions.easing.sharp,
      duration: theme.transitions.duration.enteringScreen,
    }),
    overflowX: 'hidden',
    boxShadow: 'none',
    backgroundColor: '#FAFAFB',
    height: `calc(100vh - 64px - 48px - ${theme.spacing(1)})`,
    top: '64px',
    position: 'fixed',
    left: '45px',
    bottom: '48px',
    marginTop: `3px`,
    paddingTop: 0,
    padding: 0,
  };

  const closedMixin = {
    transition: theme.transitions.create(['width', 'borderRight'], {
      easing: theme.transitions.easing.sharp,
      duration: theme.transitions.duration.leavingScreen,
    }),
    overflowX: 'hidden',
    width: 0,
    borderRight: 'none',
    boxShadow: 'none',
    backgroundColor: '#FAFAFB',
    height: `calc(100vh - 64px - 48px - ${theme.spacing(1)})`,
    top: '64px',
    position: 'fixed',
    left: '45px',
    bottom: '48px',
    marginTop: `3px`,
    paddingTop: 0,
    padding: 0,
    pointerEvents: 'none',
  };

  return {
    flexShrink: 0,
    whiteSpace: 'nowrap',
    boxSizing: 'border-box',
    variants: [],
    ...(open
      ? {
          ...openedMixin,
          '& .MuiDrawer-paper': openedMixin,
        }
      : {
          ...closedMixin,
          '& .MuiDrawer-paper': closedMixin,
        }),
  };
});
