import { Box, List, ListItem, ListItemButton, ListItemIcon, Tooltip, Divider } from '@mui/material';
import { useSelector } from 'react-redux';
import FolderOutlinedIcon from '@mui/icons-material/FolderOutlined';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons';
import { RootState } from '../../store/reduxStore';
import '../../assets/styles/Drawer.css';

type IconSidebarProps = {
  onWorkspaceClick: () => void;
  onSettingsClick: () => void;
  onDrawerToggle: () => void;
  workspaceActive: boolean;
  settingsActive: boolean;
  drawerOpen: boolean;
};

export const IconSidebar = ({ 
  onWorkspaceClick, 
  onSettingsClick, 
  onDrawerToggle,
  workspaceActive, 
  settingsActive,
  drawerOpen
}: IconSidebarProps) => {
  const isFetching = useSelector((state: RootState) => state.serverCommunication.isFetching);
  const iconBackColor = 'grey.100';
  const iconBackColorOpen = 'grey.200';

  return (
    <Box className="icon-sidebar" sx={{ borderColor: 'divider' }}>
      <List className="icon-sidebar-list">
        <ListItem disablePadding>
          <Tooltip title={drawerOpen ? "Close drawer" : "Open drawer"} placement="right" arrow>
            <ListItemButton
              onClick={onDrawerToggle}
              disabled={isFetching}
              className="icon-sidebar-button"
              sx={{
                bgcolor: drawerOpen ? iconBackColorOpen : iconBackColor,
                '&:hover': {
                  bgcolor: drawerOpen ? iconBackColorOpen : iconBackColor,
                },
              }}
            >
              <ListItemIcon className="icon-sidebar-icon">
                {drawerOpen ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />}
              </ListItemIcon>
            </ListItemButton>
          </Tooltip>
        </ListItem>
        <Divider sx={{ my: 0.5 }} />
        <ListItem disablePadding>
          <Tooltip title="Workspace" placement="right" arrow>
            <ListItemButton
              onClick={onWorkspaceClick}
              selected={workspaceActive}
              disabled={isFetching}
              className="icon-sidebar-button"
              sx={{
                '&.Mui-selected': {
                  bgcolor: 'action.selected',
                },
              }}
            >
              <ListItemIcon className="icon-sidebar-icon">
                <FolderOutlinedIcon />
              </ListItemIcon>
            </ListItemButton>
          </Tooltip>
        </ListItem>
        <ListItem disablePadding>
          <Tooltip title="Simulation Settings" placement="right" arrow>
            <ListItemButton
              onClick={onSettingsClick}
              selected={settingsActive}
              disabled={isFetching}
              className="icon-sidebar-button"
              sx={{
                '&.Mui-selected': {
                  bgcolor: 'action.selected',
                },
              }}
            >
              <ListItemIcon className="icon-sidebar-icon">
                <PlayCircleOutlinedIcon />
              </ListItemIcon>
            </ListItemButton>
          </Tooltip>
        </ListItem>
      </List>
    </Box>
  );
};
