import { Box } from '@mui/material';
import { useSelector } from 'react-redux';
import { SimpleBarScroll } from '../../components/SimpleBar';
import { WorkspaceNavigation } from './WorkspaceNavigation/WorkspaceNavigation';
import { SettingsContent } from './SettingsContent';
import { RootState } from '../../store/reduxStore';
import '../../assets/styles/Drawer.css';

type DrawerContentProps = {
  open: boolean;
  targetDirectory?: string | null;
};

export const DrawerContent = ({ open, targetDirectory }: DrawerContentProps) => {
  const drawerType = useSelector((state: RootState) => state.menu.drawerType);
  
  if (!open) return null;

  return (
    <Box className="drawer-content-container">
      <SimpleBarScroll className="drawer-content-scroll">
        {drawerType === 'settings' ? <SettingsContent /> : <WorkspaceNavigation targetDirectory={targetDirectory} />}
      </SimpleBarScroll>
    </Box>
  );
};
