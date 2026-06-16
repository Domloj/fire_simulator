import { 
  Box, 
  Typography, 
  Paper, 
  Tabs, 
  Tab, 
  TextField, 
  Switch, 
  FormControlLabel, 
  Grid, 
  Button, 
  Divider, 
  CircularProgress,
  Alert,
  Snackbar
} from '@mui/material';
import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import SaveIcon from '@mui/icons-material/Save';
import RefreshIcon from '@mui/icons-material/Refresh';
import { configurationService } from '../services/api/configurationService';
import { AppSettings, defaultSettings } from '../types/settings';
import { mapFileSystemNodeToApiDataNode } from '../model/FileSystemNode';
import { NodeTypeEnum } from '../model/NodeTypeEnum';
import { setActiveSettingId } from '../store/settingsSlice';
import { SimpleBarScroll } from '../components/SimpleBar';

// ==============================|| SETTINGS PAGE ||============================== //


interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function CustomTabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  if (value !== index) return null;

  return (
    <div
      role="tabpanel"
      id={`settings-tabpanel-${index}`}
      aria-labelledby={`settings-tab-${index}`}
      {...other}
    >
      <Box sx={{ p: 10 }}>
        {children}
      </Box>
    </div>
  );
}

export const SettingsPage = () => {
  const { settingId } = useParams();
  const dispatch = useDispatch();
  const [activeTab, setActiveTab] = useState(0);
  const [settings, setSettings] = useState<AppSettings>(defaultSettings);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [notification, setNotification] = useState<{ open: boolean; message: string; severity: 'success' | 'error' }>({
    open: false,
    message: '',
    severity: 'success'
  });

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };

  const fetchSettings = useCallback(async () => {
    if (!settingId || settingId === 'custom') {
      setSettings(defaultSettings);
      if (settingId === 'custom') {
        dispatch(setActiveSettingId('custom'));
      }
      return;
    }

    try {
      setIsLoading(true);
      dispatch(setActiveSettingId(settingId));
      const nodeData = await configurationService.getNode(settingId);
      if (nodeData.data) {
        try {
          const parsed = JSON.parse(nodeData.data);
          // Deep merge with default settings to ensure all fields exist
          setSettings({
            ...defaultSettings,
            ...parsed,
            simulation: { ...defaultSettings.simulation, ...parsed.simulation },
            support: { ...defaultSettings.support, ...parsed.support },
          });
        } catch (e) {
          console.error('[Settings] Failed to parse settings JSON:', e);
          setNotification({
            open: true,
            message: 'Failed to parse settings data. Using defaults.',
            severity: 'error'
          });
          setSettings(defaultSettings);
        }
      }
    } catch (error) {
      console.error('[Settings] Failed to fetch settings:', error);
      setNotification({
        open: true,
        message: 'Failed to load settings from server.',
        severity: 'error'
      });
    } finally {
      setIsLoading(false);
    }
  }, [settingId]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleSave = async () => {
    if (!settingId || settingId === 'custom') {
      setNotification({
        open: true,
        message: 'Cannot save "Custom" settings directly yet. Please select a configuration file.',
        severity: 'error'
      });
      return;
    }

    try {
      setIsSaving(true);
      const nodeData = await configurationService.getNode(settingId);
      const apiNode = mapFileSystemNodeToApiDataNode({
        id: settingId,
        name: nodeData.name,
        nodeType: NodeTypeEnum.FILE
      }, nodeData.parentId);
      
      apiNode.data = JSON.stringify(settings, null, 2);
      
      await configurationService.updateNode(settingId, apiNode);
      setNotification({
        open: true,
        message: 'Settings saved successfully!',
        severity: 'success'
      });
    } catch (error) {
      console.error('[Settings] Failed to save settings:', error);
      setNotification({
        open: true,
        message: 'Failed to save settings.',
        severity: 'error'
      });
    } finally {
      setIsSaving(false);
    }
  };

  const updateSimulationField = (field: keyof AppSettings['simulation'], value: any) => {
    setSettings(prev => ({
      ...prev,
      simulation: { ...prev.simulation, [field]: value }
    }));
  };

  const updateSupportField = (field: keyof AppSettings['support'], value: any) => {
    setSettings(prev => ({
      ...prev,
      support: { ...prev.support, [field]: value }
    }));
  };

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box className="settings-page-container" sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', pt: '64px' }}>
      <Paper sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', borderRadius: 0, boxShadow: 'none' }}>
        <Box sx={{ p: 3, pt: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <Box>
            <Typography variant="h4">
              Simulation Settings
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {settingId === 'custom' ? 'Custom Configuration' : `Editing: ${settingId}`}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button 
              variant="outlined" 
              startIcon={<RefreshIcon />} 
              onClick={fetchSettings}
              disabled={isSaving}
            >
              Reload
            </Button>
            <Button 
              variant="contained" 
              startIcon={<SaveIcon />} 
              onClick={handleSave}
              disabled={isSaving || settingId === 'custom'}
            >
              {isSaving ? 'Saving...' : 'Save Settings'}
            </Button>
          </Box>
        </Box>
        
        <Divider />
        
        <Box sx={{ borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}>
          <Tabs 
            value={activeTab} 
            onChange={handleTabChange} 
            aria-label="settings tabs"
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label="Simulation" />
            <Tab label="Support & LLM" />
          </Tabs>
        </Box>

        <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
          <SimpleBarScroll sx={{ height: '100%' }}>
            <Box sx={{ p: 4, pt: 4, minWidth: 800 }}>
              {/* SIMULATION TAB */}
              <CustomTabPanel value={activeTab} index={0}>
                <Grid sx={{ pt: 6 }} container spacing={12} rowSpacing={18}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Tick Interval (seconds)"
                      type="number"
                      inputProps={{ step: 0.1, min: 0.1 }}
                      InputLabelProps={{ shrink: true }}
                      value={settings.simulation.tickInterval}
                      onChange={(e) => updateSimulationField('tickInterval', parseFloat(e.target.value))}
                      helperText="Time between simulation steps"
                      variant="outlined"
                      sx={{ m: '10px' }}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Fire Fighters Multiplier"
                      type="number"
                      inputProps={{ min: 1 }}
                      InputLabelProps={{ shrink: true }}
                      value={settings.simulation.fireFightersMultiplier}
                      onChange={(e) => updateSimulationField('fireFightersMultiplier', parseInt(e.target.value))}
                      helperText="Efficiency multiplier for fire fighters"
                      variant="outlined"
                      sx={{ m: '10px' }}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Fire Level Multiplier"
                      type="number"
                      inputProps={{ min: 1 }}
                      InputLabelProps={{ shrink: true }}
                      value={settings.simulation.fireLevelMultiplier}
                      onChange={(e) => updateSimulationField('fireLevelMultiplier', parseInt(e.target.value))}
                      helperText="Intensity multiplier for fire spread"
                      variant="outlined"
                      sx={{ m: '10px' }}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Fire Spread Probability Multiplier"
                      type="number"
                      inputProps={{ step: 0.01, min: 0 }}
                      InputLabelProps={{ shrink: true }}
                      value={settings.simulation.fireSpreadProbMultiplier}
                      onChange={(e) => updateSimulationField('fireSpreadProbMultiplier', parseFloat(e.target.value))}
                      helperText="Probability multiplier for fire jumping between sectors"
                      variant="outlined"
                      sx={{ m: '10px' }}
                    />
                  </Grid>
                </Grid>
              </CustomTabPanel>

              {/* SUPPORT TAB */}
              <CustomTabPanel value={activeTab} index={1}>
                <Grid sx={{ pt: 6 }} container spacing={12} rowSpacing={18}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      select
                      fullWidth
                      label="Recommendation Mode"
                      InputLabelProps={{ shrink: true }}
                      value={settings.support.recommendationMode}
                      onChange={(e) => updateSupportField('recommendationMode', e.target.value)}
                      SelectProps={{ native: true }}
                      variant="outlined"
                      sx={{ m: '10px' }}
                    >
                      <option value="heuristic">Heuristic</option>
                      <option value="llm">LLM</option>
                      <option value="hybrid">Hybrid</option>
                    </TextField>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      select
                      fullWidth
                      label="Agent Decision Mode"
                      InputLabelProps={{ shrink: true }}
                      value={settings.support.agentDecisionMode}
                      onChange={(e) => updateSupportField('agentDecisionMode', e.target.value)}
                      SelectProps={{ native: true }}
                      variant="outlined"
                      sx={{ m: '10px' }}
                    >
                      <option value="heuristic">Heuristic</option>
                      <option value="llm">LLM</option>
                      <option value="hybrid">Hybrid</option>
                    </TextField>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Box sx={{ p: 2, m: '10px', border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                      <FormControlLabel
                        control={
                          <Switch 
                            checked={settings.support.enableLlmCoordination} 
                            onChange={(e) => updateSupportField('enableLlmCoordination', e.target.checked)} 
                          />
                        }
                        label="Enable LLM Coordination"
                      />
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Box sx={{ p: 2, m: '10px', border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                      <FormControlLabel
                        control={
                          <Switch 
                            checked={settings.support.enableAgentCommunication} 
                            onChange={(e) => updateSupportField('enableAgentCommunication', e.target.checked)} 
                          />
                        }
                        label="Enable Agent-to-Agent Communication"
                      />
                    </Box>
                  </Grid>
                </Grid>
              </CustomTabPanel>
            </Box>
          </SimpleBarScroll>
        </Box>
      </Paper>

      <Snackbar 
        open={notification.open} 
        autoHideDuration={6000} 
        onClose={() => setNotification(prev => ({ ...prev, open: false }))}
      >
        <Alert 
          onClose={() => setNotification(prev => ({ ...prev, open: false }))} 
          severity={notification.severity} 
          sx={{ width: '100%' }}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};


