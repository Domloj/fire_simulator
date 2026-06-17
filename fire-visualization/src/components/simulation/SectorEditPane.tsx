import { FC, useMemo } from 'react';
import { Box, Paper, Typography, Divider } from '@mui/material';
import { useSelector } from 'react-redux';
import { RootState } from '../../store/reduxStore';
import { SectorFormPart } from '../../features/configuration/SectorConfiguration';
import { Formik, Form } from 'formik';
import { Configuration } from '../../model/configuration';
import '../../assets/styles/SectorEditPane.css';

export const SectorEditPane: FC = () => {
  const { configuration, currentSectorId } = useSelector((state: RootState) => state.mapConfiguration);

  const selectedSector = useMemo(() => {
    if (currentSectorId === null || !configuration.sectors) {
      return null;
    }
    return configuration.sectors.find((s) => s.sectorId === currentSectorId) || null;
  }, [configuration, currentSectorId]);

  if (!selectedSector) {
    return (
      <Paper className="sector-edit-pane" elevation={2}>
        <Box sx={{ p: 2, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Select a sector on the map to edit
          </Typography>
        </Box>
      </Paper>
    );
  }

  return (
    <Paper className="sector-edit-pane" elevation={2}>
      <Box sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Sector {selectedSector.sectorId} Configuration
        </Typography>
        <Divider sx={{ mb: 2 }} />
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          <Formik
            initialValues={configuration}
            onSubmit={() => {}}
            enableReinitialize
          >
            <Form>
              <SectorFormPart obj={selectedSector} readonly={false} />
            </Form>
          </Formik>
        </Box>
      </Box>
    </Paper>
  );
};
