import { useCallback } from 'react';
import { useSelector} from 'react-redux';
import { Button } from '@mui/material';
import { RootState } from '../../store/reduxStore';

const DownloadConfigurationButton: React.FC = () => {
  const mapConfiguration = useSelector((state: RootState) => state.mapConfiguration);

  const downloadFile = useCallback(() => {
    if (!mapConfiguration?.configuration) {
      return;
    }

    // create file in browser
    const fileName = mapConfiguration.configuration.forestName || "simulation-configuration";
    const json = JSON.stringify(mapConfiguration.configuration, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const href = URL.createObjectURL(blob);
  
    const link = document.createElement("a");
    link.href = href;
    link.download = fileName + ".json";
    document.body.appendChild(link);
    link.click();
  
    document.body.removeChild(link);
    URL.revokeObjectURL(href);
  }, [mapConfiguration]);
  
  return (
    <Button
      variant="contained"
      color='secondary'
      onClick={downloadFile}
      sx={{ width: '250px' }}      
    >
      Download Configuration
    </Button>
  );
};

export default DownloadConfigurationButton;
