import { Box, Typography, List, ListItemButton, ListItemText, ListItemIcon, Divider, CircularProgress } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { configurationService } from '../../services/api/configurationService';
import {
  FileSystemNode,
  mapApiDataNodesToFileSystemNodes,
} from '../../model/FileSystemNode';
import { NodeTypeEnum } from '../../model/NodeTypeEnum';
import SettingsIcon from '@mui/icons-material/Settings';
import ConstructionIcon from '@mui/icons-material/Construction';
import { setActiveSettingId } from '../../store/settingsSlice';
import '../../assets/styles/SettingsContent.css';

// ==============================|| SETTINGS CONTENT ||============================== //

export const SettingsContent = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { settingId } = useParams();
  const [settingsFiles, setSettingsFiles] = useState<FileSystemNode[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchSettingsFolder = useCallback(async () => {
    try {
      setIsLoading(true);
      const allNodes = await configurationService.getNodes();
      const fileSystemNodes = mapApiDataNodesToFileSystemNodes(allNodes);
      
      const settingsFolder = fileSystemNodes.find(node => 
        node.nodeType === NodeTypeEnum.FOLDER && node.name.toLowerCase() === 'settings'
      );
      
      if (settingsFolder) {
        const children = await configurationService.getNodeChildren(settingsFolder.id);
        const convertedChildren = mapApiDataNodesToFileSystemNodes(children);
        
        // Show all files in settings folder
        const files = convertedChildren.filter(node => node.nodeType === NodeTypeEnum.FILE);
        setSettingsFiles(files);
      }
    } catch (error) {
      console.error('[Settings] Failed to fetch settings folder:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettingsFolder();
  }, [fetchSettingsFolder]);

  const handleSettingClick = (id: string) => {
    dispatch(setActiveSettingId(id));
    navigate(`/settings/${id}`);
  };

  const handleCustomClick = () => {
    dispatch(setActiveSettingId('custom'));
    navigate('/settings/custom');
  };

  return (
    <Box className="settings-container" sx={{ p: 2 }}>
      <Typography variant="h6" className="settings-title" sx={{ mb: 2 }}>
        Simulation Settings
      </Typography>
      
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
          <CircularProgress size={24} />
        </Box>
      ) : (
        <List component="nav" sx={{ width: '100%' }}>
          {settingsFiles.map((file) => (
            <ListItemButton
              key={file.id}
              selected={settingId === file.id}
              onClick={() => handleSettingClick(file.id)}
              sx={{ borderRadius: 1, mb: 0.5 }}
            >
              <ListItemText 
                primary={file.name} 
                primaryTypographyProps={{ variant: 'body2' }}
              />
            </ListItemButton>
          ))}
          
          <Divider sx={{ my: 1 }} />
          
          <ListItemButton
            selected={settingId === 'custom'}
            onClick={handleCustomClick}
            sx={{ borderRadius: 1 }}
          >
            <ListItemIcon sx={{ minWidth: 36 }}>
              <ConstructionIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText 
              primary="Custom Settings" 
              primaryTypographyProps={{ variant: 'body2', fontWeight: 'bold' }}
            />
          </ListItemButton>
        </List>
      )}
    </Box>
  );
};


