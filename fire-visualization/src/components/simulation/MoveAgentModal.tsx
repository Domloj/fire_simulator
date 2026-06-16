import { useState, useCallback } from 'react';
import { 
  Dialog, 
  DialogTitle, 
  DialogContent, 
  DialogActions, 
  Button
} from '@mui/material';
import { MapWrapper } from '../maps/MapWrapper';
import { FireBrigadeMap } from '../maps/FireBrigadeMap';
import { ForesterMap } from '../maps/ForesterMap';

type MoveAgentModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onMove: (targetSectorId: number) => void;
  agentId: number;
  agentType: 'Fire Brigade' | 'Forester Patrol';
  currentSectorId: number;
};

export const MoveAgentModal: React.FC<MoveAgentModalProps> = ({
  isOpen,
  onClose,
  onMove,
  agentId,
  agentType,
  currentSectorId,
}) => {
  const [targetSector, setTargetSector] = useState<number | null>(null);

  const handleClose = useCallback(() => {
    setTargetSector(null);
    onClose();
  }, [onClose]);

  const onSelectTargetSector = useCallback((sectorId: number) => {
    setTargetSector(sectorId);
  }, []);

  const submitTargetSector = useCallback(() => {
    if (targetSector === null) {
      return;
    }
    onMove(targetSector);
    handleClose();
  }, [targetSector, onMove, handleClose]);

  const dialogTitle = agentType === 'Fire Brigade' 
    ? `Move Brigade FB-${agentId}` 
    : `Move Forester Patrol FP-${agentId}`;

  const MapComponent = agentType === 'Fire Brigade' ? FireBrigadeMap : ForesterMap;

  return (
    <Dialog
      open={isOpen}
      onClose={handleClose}
      fullWidth={true}
      maxWidth='sm'
      aria-labelledby="alert-dialog-title"
      aria-describedby="alert-dialog-description"
    >
      <DialogTitle id="alert-dialog-title" sx={{ textAlign: 'center' }}>
        {dialogTitle}
      </DialogTitle>
      <DialogContent>
        <MapWrapper>
          <MapComponent targetSectorId={targetSector} onClickHandler={onSelectTargetSector} />
        </MapWrapper>
      </DialogContent>
      <DialogActions>
        <Button variant="contained" color='primary' disabled={targetSector === null} onClick={submitTargetSector}>
          Move
        </Button>
        <Button onClick={handleClose} variant="contained" color='error'>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};
