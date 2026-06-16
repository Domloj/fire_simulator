import { useDispatch, useSelector } from "react-redux";
import { AppDispatch, RootState } from "../../store/reduxStore";
import { useState, useCallback } from "react";
import { Button, Dialog, DialogTitle, DialogContent, Divider, List, ListItem, DialogActions } from "@mui/material";
import { Camera } from "../../model/camera";
import { FireBrigade } from "../../model/FireBrigade";
import { ForesterPatrol } from "../../model/ForesterPatrol";
import { Sensor } from "../../model/sensor";
import { getObjectsInSector } from '@shared/utils/getObjectsInSector';
import RenderSimulationItem from "./RenderSimulationItem";
import { MapWrapper } from "../maps/MapWrapper";
import { MainMap } from "../maps/MainMap";
import { FireBrigadeMap } from "../maps/FireBrigadeMap";
import { sendBrigadeOrForesterMoveOrder } from "../../store/serverCommunicationReducers";
import { ForesterMap } from "../maps/ForesterMap";

type Props = {
   forestPatrolID: number;
}

export default function ForestPatrolDialog(props: Props) {
   const {
      configuration: mapConfiguration,
      currentSectorId,
   } = useSelector((state: RootState) => state.mapConfiguration);

   const dispatch: AppDispatch = useDispatch();

   const [targetSector, setTargetSector] = useState<number | null>(null);
   const [open, setOpen] = useState(false);

   const handleClickOpen = useCallback(() => {
      setOpen(true);
   }, []);

   const handleClose = useCallback(() => {
      setTargetSector(null);
      setOpen(false);
   }, []);

   const onSelectTargetSector = useCallback((sectorId: number) => {
      setTargetSector(sectorId);
   }, []);

   const submitTargetSector = useCallback(() => {
      if(targetSector === null) {
         return;
      }
      dispatch(sendBrigadeOrForesterMoveOrder(props.forestPatrolID, targetSector, "forester", 'manual'));
      handleClose();
   }, [targetSector, props.forestPatrolID, dispatch, handleClose]);

   // Guard po wszystkich hookach (Rules of Hooks) — wcześniejszy return między
   // useCallback crashował render przy zmianie currentSectorId (biały ekran).
   if (currentSectorId === null) {
      return null;
   }

   return (
      <>
         <Button variant="contained" sx={{ width: '150px' }} onClick={handleClickOpen}>Move</Button>

         <Dialog
            open={open}
            onClose={handleClose}
            fullWidth={true}
            maxWidth='sm'
            aria-labelledby="alert-dialog-title"
            aria-describedby="alert-dialog-description"
         >
            <DialogTitle id="alert-dialog-title" sx={{ textAlign: 'center' }}>
               Move forest patrol
            </DialogTitle>
            <DialogContent>
               <MapWrapper>
                  <ForesterMap targetSectorId={targetSector} onClickHandler={onSelectTargetSector}/>
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
      </>
   );
}
