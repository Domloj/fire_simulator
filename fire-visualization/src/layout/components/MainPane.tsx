import { ReactNode } from 'react';
import { Box, Toolbar, useTheme } from '@mui/material';
import '../../assets/styles/MainLayout.css';

type MainPaneProps = {
  open: boolean;
  children: ReactNode;
};

export const MainPane = ({ open, children }: MainPaneProps) => {
  const theme = useTheme();
  const mainPaneClasses = `main-pane ${open ? 'main-pane-drawer-open' : 'main-pane-drawer-closed'}`;

  return (
    <Box
      component="main"
      className={mainPaneClasses}
      sx={{
        borderTop: `1px solid ${theme.palette.divider}`,
        transition: theme.transitions.create(['width', 'margin-left'], {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.leavingScreen,
        }),
      }}
    >
      <Toolbar />
      <Box className="main-pane-content">{children}</Box>
    </Box>
  );
};
