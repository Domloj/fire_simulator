import { styled } from '@mui/material/styles';
import AppBar from '@mui/material/AppBar';

export const AppBarStyled = styled(AppBar)(
  ({ theme }) => ({
    zIndex: theme.zIndex.drawer + 1,
    width: '100%',
    left: 0,
    right: 0,
    borderBottom: `1px solid ${theme.palette.divider}`,
  }),
);
