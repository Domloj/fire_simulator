/* eslint-disable @typescript-eslint/no-explicit-any */

import { useMemo, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';

// material-ui
import { useTheme } from '@mui/material/styles';
import { Box, Drawer, useMediaQuery } from '@mui/material';

// project import
import { DrawerContent } from './DrawerContent';
import { MiniDrawerStyled } from './MiniDrawerStyled';
import { IconSidebar } from './IconSidebar';
import { RootState } from '../../store/reduxStore';
import { openDrawer, setDrawerType } from '../../store/menuSlice';

type MainDrawerProps = {
  open: boolean;
  handleDrawerToggle: () => void;
  window?: any;
};

export const MainDrawer = ({ open, handleDrawerToggle, window }: MainDrawerProps) => {
  const theme = useTheme();
  const matchDownMD = useMediaQuery(theme.breakpoints.down('lg'));
  const dispatch = useDispatch();
  const drawerType = useSelector((state: RootState) => state.menu.drawerType);
  const [targetDirectory, setTargetDirectory] = useState<string | null>(null);

  const container = window !== undefined ? () => window().document.body : undefined;
  const drawerContent = useMemo(() => <DrawerContent open={open} targetDirectory={targetDirectory} />, [open, targetDirectory]);

  const handleWorkspaceClick = () => {
    setTargetDirectory('root');
    if (drawerType === 'workspace' && open) {
      handleDrawerToggle();
    } else {
      dispatch(setDrawerType({ drawerType: 'workspace' }));
      if (!open) {
        handleDrawerToggle();
      }
    }
  };

  const handleSettingsClick = async () => {
    try {
      const { configurationService } = await import('../../services/api/configurationService');
      const { mapApiDataNodesToFileSystemNodes, mapFileSystemNodeToApiDataNode, mapApiDataNodeToFileSystemNode } = await import('../../model/FileSystemNode');
      const { NodeTypeEnum } = await import('../../model/NodeTypeEnum');
      
      const allNodes = await configurationService.getNodes();
      const fileSystemNodes = mapApiDataNodesToFileSystemNodes(allNodes);
      
      let settingsFolder = fileSystemNodes.find(node => 
        node.nodeType === NodeTypeEnum.FOLDER && node.name.toLowerCase() === 'settings'
      );
      
      if (!settingsFolder) {
        const settingsFolderNode = {
          id: 'null',
          name: 'settings',
          nodeType: NodeTypeEnum.FOLDER,
        };
        
        const apiNode = mapFileSystemNodeToApiDataNode(settingsFolderNode, null);
        const createdFolder = await configurationService.createNode(apiNode);
        settingsFolder = mapApiDataNodeToFileSystemNode(createdFolder);
      }
      
      if (settingsFolder) {
        const settingsChildren = await configurationService.getNodeChildren(settingsFolder.id);
        const settingsFileSystemNodes = mapApiDataNodesToFileSystemNodes(settingsChildren);
        
        const simSettingsExists = settingsFileSystemNodes.some(node => 
          node.name.toLowerCase() === 'sim_settings' || node.name.toLowerCase() === 'sim_settings.json'
        );
        
        if (!simSettingsExists) {
          const simSettingsNode = {
            id: 'null',
            name: 'sim_settings',
            nodeType: NodeTypeEnum.FILE,
          };
          
          const apiNode = mapFileSystemNodeToApiDataNode(simSettingsNode, settingsFolder.id);
          apiNode.data = JSON.stringify({});
          
          await configurationService.createNode(apiNode);
        }
      }
      
      setTargetDirectory('settings');
    } catch (error) {
      console.error('[Settings] Failed to check/create settings folder or sim_settings:', error);
      setTargetDirectory('settings');
    }
    
    if (drawerType === 'settings' && open) {
      handleDrawerToggle();
    } else {
      dispatch(setDrawerType({ drawerType: 'settings' }));
      if (!open) {
        handleDrawerToggle();
      }
    }
  };

  return (
    <Box
      component="nav"
      sx={{ flexShrink: { md: 0 }, zIndex: 1300 }}
      aria-label="mailbox folders"
    >
      <IconSidebar 
        onWorkspaceClick={handleWorkspaceClick} 
        onSettingsClick={handleSettingsClick}
        onDrawerToggle={handleDrawerToggle}
        workspaceActive={open && drawerType === 'workspace'} 
        settingsActive={open && drawerType === 'settings'}
        drawerOpen={open}
      />
      {!matchDownMD ? (
        <MiniDrawerStyled
          variant="permanent"
          open={open}
        >
          {drawerContent}
        </MiniDrawerStyled>
      ) : (
        <Drawer
          container={container}
          variant="temporary"
          open={open}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', lg: 'none' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: 215,
              borderRight: `1px solid ${theme.palette.divider}`,
              backgroundImage: 'none',
              backgroundColor: '#FAFAFB',
              boxShadow: 'inherit',
              height: `calc(100vh - 64px - 48px - ${theme.spacing(1)})`,
              top: '64px',
              left: '45px',
              bottom: '48px',
              marginTop: `2px`,
              paddingTop: 0,
              padding: 0,
            },
          }}
        >
          {open && drawerContent}
        </Drawer>
      )}
    </Box>
  );
};
