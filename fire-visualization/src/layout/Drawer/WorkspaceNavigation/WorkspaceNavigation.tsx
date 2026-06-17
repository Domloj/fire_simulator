import { Box, Typography, Button } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { FileAddOutlined, FolderAddOutlined, FolderOpenOutlined } from '@ant-design/icons';
import { FileSystemComponent } from './FileSystemComponent';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { configurationService } from '../../../services/api/configurationService';
import {
  FileSystemNode,
  mapApiDataNodeToFileSystemNode,
  mapApiDataNodesToFileSystemNodes,
  mapFileSystemNodeToApiDataNode,
} from '../../../model/FileSystemNode';
import { NodeTypeEnum } from '../../../model/NodeTypeEnum';
import { Configuration } from '../../../model/configuration';
import { SelectWorkspaceModal } from './SelectWorkspaceModal';
import { CreateFolderModal } from './CreateFolderModal';
import { CreateConfigurationModal } from './CreateConfigurationModal';
import { FormikProps } from 'formik';
import { useDispatch } from 'react-redux';
import {
  setConfiguration,
  setCurrentSectorId,
  setFileSystemNode,
} from '../../../store/mapConfigurationSlice';
import { setDrawerType, openDrawer } from '../../../store/menuSlice';
import { Sector } from '../../../model/sector';

export type FileSystemNodes = { parent: FileSystemNode | null; nodes: FileSystemNode[] };

type WorkspaceNavigationProps = {
  targetDirectory?: string | null; // 'root' | 'settings' | null
};

export const WorkspaceNavigation: React.FC<WorkspaceNavigationProps> = ({ targetDirectory }) => {
  const theme = useTheme();
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const [isSelectWorkspaceModalVisible, setIsSelectWorkspaceModalVisible] = useState(false);
  const [workspace, setWorkspace] = useState<FileSystemNodes>(() => {
    // Always start at root (parent = null) on initial load
    // Don't restore from localStorage to avoid showing root as a folder
    return {
      parent: null,
      nodes: [],
    };
  });

  // Persist workspace to localStorage whenever it changes (but not for root)
  useEffect(() => {
    if (workspace.parent) {
      // Only save if parent is not root
      const isRoot = workspace.parent.name?.toLowerCase() === 'root' || !workspace.parent.name;
      if (!isRoot) {
        localStorage.setItem('fire-sim-workspace', JSON.stringify(workspace.parent));
      } else {
        // Clear localStorage when at root
        localStorage.removeItem('fire-sim-workspace');
      }
    } else {
      // Clear localStorage when at root (parent = null)
      localStorage.removeItem('fire-sim-workspace');
    }
  }, [workspace.parent]);

  const [isNewFolderModalVisible, setIsNewFolderModalVisible] = useState(false);
  const [newFolderName, setNewFolderName] = useState<string | null>(null);

  const [isNewConfigurationModalVisible, setIsNewConfigurationModalVisible] = useState(false);
  const [newConfigurationName, setNewConfigurationName] = useState<string | null>(null);

  // URL is now handled by the API service

  const [allNodes, setAllNodes] = useState<FileSystemNodes>({ parent: null, nodes: [] });
  const [selectedMenuItem, setSelectedMenuItem] = useState<FileSystemNode | null>(null);
  const [selectedModalMenuItem, setSelectedModalMenuItem] = useState<FileSystemNode | null>(null);

  const configurationFormRef = useRef<FormikProps<Configuration> | null>(null);

  const handleSelectWorkspaceCloseModal = useCallback(() => {
    setIsSelectWorkspaceModalVisible(false);
    setSelectedMenuItem(null);
    setSelectedModalMenuItem(null);
  }, []);

  const fetchAllNodes = useCallback(async (): Promise<FileSystemNode[]> => {
    try {
      const data = await configurationService.getNodes();
      
      // Build the entire tree first
      const fullTree = mapApiDataNodesToFileSystemNodes(data);
      
      // Find the root node in the tree
      const rootNode = fullTree.find(node => node.name.toLowerCase() === 'root');
      
      if (rootNode && rootNode.contents) {
        // Return only the children of the root node, filtering out 'settings'
        return rootNode.contents.filter(node => node.name.toLowerCase() !== 'settings');
      }
      
      // Fallback: if no root node found, return the full tree (filtered)
      return fullTree.filter(node => node.name.toLowerCase() !== 'root' && node.name.toLowerCase() !== 'settings');
    } catch (error) {
      console.error('[Workspace] Failed to fetch nodes:', error);
      return [];
    }
  }, []);

  const fetchRootChildren = useCallback(async (): Promise<FileSystemNode[]> => {
    return await fetchAllNodes();
  }, [fetchAllNodes]);

  const handleOpenSelectWorkspaceModal = useCallback(async () => {
    setIsSelectWorkspaceModalVisible(true);
    setSelectedMenuItem(null);
    setSelectedModalMenuItem(null);
    const fetchedNodes = await fetchAllNodes();
    setAllNodes((prevState) => ({ ...prevState, nodes: fetchedNodes }));
  }, [fetchAllNodes]);

  const fetchChildNodes = useCallback(async () => {
    try {
      if (workspace.parent) {
        const data = await configurationService.getNodeChildren(workspace.parent.id);
        const convertedData = mapApiDataNodesToFileSystemNodes(data);
        setWorkspace((prevState) => ({ ...prevState, nodes: convertedData }));
      } else {
        // Show root's children
        const rootChildren = await fetchRootChildren();
        setWorkspace((prevState) => ({ ...prevState, nodes: rootChildren }));
      }
    } catch (error) {
      console.error('[Workspace] Failed to fetch child nodes:', error);
    }
  }, [workspace.parent, fetchRootChildren]);

  // Always fetch children when parent changes
  useEffect(() => {
    fetchChildNodes();
  }, [fetchChildNodes, workspace.parent]);

  // On mount, ensure we're at root (parent = null)
  useEffect(() => {
    // Reset to root on initial mount
    if (workspace.parent !== null) {
      setWorkspace({ parent: null, nodes: [] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Handle target directory changes
  useEffect(() => {
    if (targetDirectory === 'root') {
      // Always reset to root (parent = null) when targetDirectory is 'root'
      setWorkspace({ parent: null, nodes: [] });
      setSelectedMenuItem(null);
    } else if (targetDirectory === 'settings') {
      const findAndSetSettingsFolder = async () => {
        try {
          // Get root's children to find settings folder
          const rootChildren = await fetchRootChildren();
          const settingsFolder = rootChildren.find(node => 
            node.nodeType === NodeTypeEnum.FOLDER && node.name.toLowerCase() === 'settings'
          );
          
          if (settingsFolder) {
            const data = await configurationService.getNode(settingsFolder.id);
            const convertedData = mapApiDataNodeToFileSystemNode(data);
            setWorkspace({ parent: convertedData, nodes: [] });
          } else {
            // Settings folder doesn't exist yet, will be created by MainDrawer
            // For now, show root
            setWorkspace({ parent: null, nodes: [] });
          }
        } catch (error) {
          console.error('[Workspace] Failed to find settings folder:', error);
          setWorkspace({ parent: null, nodes: [] });
        }
      };
      findAndSetSettingsFolder();
    }
  }, [targetDirectory, fetchRootChildren]);

  const selectWorkspace = useCallback(async () => {
    try {
      if (selectedModalMenuItem) {
        const data = await configurationService.getNode(selectedModalMenuItem.id);
        const convertedData = mapApiDataNodeToFileSystemNode(data);
        setWorkspace({ parent: convertedData, nodes: [] });
      }
    } catch (error) {
      console.error('[Workspace] Failed to select workspace:', error);
    }

    handleSelectWorkspaceCloseModal();
  }, [handleSelectWorkspaceCloseModal, selectedModalMenuItem]);

  const handleOpenNewFolderModal = useCallback((): void => {
    setIsNewFolderModalVisible(true);
    setSelectedMenuItem(null);
    setSelectedModalMenuItem(null);
    setNewFolderName(null);
  }, []);

  const handleCloseNewFolderModal = useCallback((): void => {
    setIsNewFolderModalVisible(false);
    setSelectedMenuItem(null);
    setSelectedModalMenuItem(null);
    setNewFolderName(null);
  }, []);

  const handleOpenNewConfigurationModal = useCallback((): void => {
    setIsNewConfigurationModalVisible(true);
    setNewConfigurationName(null);
  }, []);

  const handleCloseNewConfigurationModal = useCallback((): void => {
    setIsNewConfigurationModalVisible(false);
    setNewConfigurationName(null);
  }, []);

  const handleCreateFolder = useCallback(async () => {
    if (selectedModalMenuItem && newFolderName) {
      const newFolder: FileSystemNode = {
        id: 'null',
        name: newFolderName,
        nodeType: NodeTypeEnum.FOLDER,
      };

      try {
        await configurationService.createNode(
          mapFileSystemNodeToApiDataNode(newFolder, selectedModalMenuItem.id)
        );
      } catch (error) {
        console.error('[Workspace] Failed to create folder:', error);
      }
    }

    fetchChildNodes();
    handleCloseNewFolderModal();
  }, [fetchChildNodes, handleCloseNewFolderModal, newFolderName, selectedModalMenuItem]);

  const handleCreateConfiguration = useCallback(async () => {
    if ((workspace.parent || selectedMenuItem) && newConfigurationName) {
      if (configurationFormRef.current) {
        await configurationFormRef.current.submitForm();
      }
    }
    fetchChildNodes();
    handleCloseNewConfigurationModal();
  }, [fetchChildNodes, handleCloseNewConfigurationModal, newConfigurationName, selectedMenuItem, workspace.parent]);

  const handleSubmit = async (values: Configuration) => {
    if (!newConfigurationName) return;
    if (!(workspace.parent || selectedMenuItem)) return;

    const sectors = Configuration.createSectors(values);
    const forestConfigurationWithSectors = { ...values, sectors };

    const newConfiguration: FileSystemNode = {
      id: 'null',
      name: newConfigurationName,
      nodeType: NodeTypeEnum.FILE,
    };
    const parentId = selectedMenuItem ? selectedMenuItem.id : workspace.parent?.id;
    if (!parentId) return;

    const newConfigurationMapped = mapFileSystemNodeToApiDataNode(newConfiguration, parentId);
    newConfigurationMapped.data = JSON.stringify(forestConfigurationWithSectors);
    
    // const aaaa = JSON.parse(newConfigurationMapped.data)
    // aaaa.sectors.forEach((sector: Sector) => {
    //   sector.row+=1;
    //   sector.column+=1;
    // })
    // newConfigurationMapped.data = JSON.stringify(aaaa);
    try {
      await configurationService.createNode(newConfigurationMapped);
    } catch (error) {
      console.error('[Workspace] Failed to create configuration:', error);
    }
  };

  return (
    <Box
      sx={{
        boxSizing: 'border-box',
        width: '100%',
        paddingX: 1,
        backgroundImage: 'none',
        boxShadow: 'inherit',
        bgcolor: '#FAFAFB',
        height: '100%',
        overflow: 'auto',
      }}
    >
      <Box sx={{ margin: 0, padding: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography
          sx={{
            color: 'secondary.main',
          }}
          variant="h6"
          component="div"
        >
          Workspace
        </Typography>
        <Box>
          <Button
            disabled={selectedMenuItem?.nodeType === NodeTypeEnum.FILE}
            sx={{ color: 'secondary.main', minWidth: 0 }}
            onClick={handleOpenNewConfigurationModal}
          >
            <FileAddOutlined style={{ fontSize: 20 }} />
          </Button>
          <Button
            sx={{ color: 'secondary.main', minWidth: 0 }}
            disabled={selectedMenuItem?.nodeType === NodeTypeEnum.FILE}
            onClick={handleOpenNewFolderModal}
          >
            <FolderAddOutlined style={{ fontSize: 20 }} />
          </Button>
          <Button
            onClick={handleOpenSelectWorkspaceModal}
            sx={{ color: 'secondary.main', minWidth: 0 }}
          >
            <FolderOpenOutlined style={{ fontSize: 20 }} />
          </Button>
        </Box>
      </Box>

      <SelectWorkspaceModal
        isOpen={isSelectWorkspaceModalVisible}
        nodesData={allNodes}
        selectedNode={selectedModalMenuItem}
        setSelectedNode={setSelectedModalMenuItem}
        selectWorkspace={selectWorkspace}
        closeModal={handleSelectWorkspaceCloseModal}
      />

      <CreateFolderModal
        isOpen={isNewFolderModalVisible}
        newFolderName={newFolderName}
        setNewFolderName={setNewFolderName}
        nodesData={workspace}
        selectedNode={selectedModalMenuItem}
        setSelectedNode={setSelectedModalMenuItem}
        handleCreateFolder={handleCreateFolder}
        closeModal={handleCloseNewFolderModal}
      />

      <CreateConfigurationModal
        isOpen={isNewConfigurationModalVisible}
        newConfigurationName={newConfigurationName}
        setNewConfigurationName={setNewConfigurationName}
        nodesData={workspace}
        selectedNode={selectedMenuItem}
        configurationFormRef={configurationFormRef}
        handleCreateConfiguration={handleCreateConfiguration}
        handleSubmit={handleSubmit}
        closeModal={handleCloseNewConfigurationModal}
      />

      <FileSystemComponent
        data={workspace}
        selected={selectedMenuItem}
        onItemSelected={setSelectedMenuItem}
        inSelectWorkspace={false}
        onFileDoubleClick={async () => {
          // TODO firstly we should check
          // if there are any unsaved changes in the currently open configuration
          if (!selectedMenuItem) return;

          // Check if this is the sim_settings file
          const isSimSettings = selectedMenuItem.name.toLowerCase() === 'sim_settings' || selectedMenuItem.name.toLowerCase() === 'sim_settings.json';
          
          if (isSimSettings) {
            dispatch(setDrawerType({ drawerType: 'settings' }));
            dispatch(openDrawer({ drawerOpen: true }));
            return;
          }

          // Check if user is trying to access sim_settings but it doesn't exist
          // This handles the case where user clicks on a non-existent file expecting it to be sim_settings
          // We'll create it if needed when they click the settings icon instead

          try {
            const node = await configurationService.getNode(selectedMenuItem.id);
            if (node.data === null) return;

          const selectedConfiguration = JSON.parse(node.data) as Configuration;

          dispatch(
            setConfiguration({
              configuration: selectedConfiguration,
            }),
          );
          dispatch(
            setFileSystemNode({
              fileSystemNode: selectedMenuItem,
            }),
          );
          dispatch(
            setCurrentSectorId({
              currentSectorId: null,
            }),
          );
          
          // Navigate to main page to show the map
          navigate('/');
          } catch (error) {
            console.error('[Workspace] Failed to load configuration:', error);
          }
        }}
      />
    </Box>
  );
};
