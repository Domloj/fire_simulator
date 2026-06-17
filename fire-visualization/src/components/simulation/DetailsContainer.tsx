import { Button, Divider, List, ListItem, Typography } from "@mui/material";
import { useSelector } from "react-redux";
import { RootState } from "../../store/reduxStore";
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import { useState, useCallback, useMemo } from "react";
import { getObjectsInSector } from '@shared/utils/getObjectsInSector';
import { Camera, isCamera } from "../../model/camera";
import { FireBrigade } from "../../model/FireBrigade";
import { ForesterPatrol, isForesterPatrol } from "../../model/ForesterPatrol";
import { Sensor, isSensor } from "../../model/sensor";
import RenderSimulationItem from "./RenderSimulationItem";

const DetailsContainer = () => {
   const {
      configuration: mapConfiguration,
      currentSectorId,
   } = useSelector((state: RootState) => state.mapConfiguration);

   const [open, setOpen] = useState(false);

   const handleClickOpen = useCallback(() => {
      setOpen(true);
   }, []);

   const handleClose = useCallback(() => {
      setOpen(false);
   }, []);

   const sectorObjects = useMemo(() => {
      if (currentSectorId === null) {
         return [];
      }
      const sector = mapConfiguration.sectors[currentSectorId - 1];
      return [
         ["Sensors", getObjectsInSector(sector, mapConfiguration.sensors)],
         ["Cameras", getObjectsInSector(sector, mapConfiguration.cameras)],
         ["Fire Brigades", getObjectsInSector(sector, mapConfiguration.fireBrigades)],
         ["Forester Patrols", getObjectsInSector(sector, mapConfiguration.foresterPatrols)],
      ] as [string, (Sensor | Camera | FireBrigade | ForesterPatrol)[]][];
   }, [mapConfiguration, currentSectorId]);

   if (currentSectorId === null) {
      return null;
   }

   return (
      <>
         <Button variant="contained" sx={{ width: '150px' }} onClick={handleClickOpen}>Details</Button>

         <Dialog
            open={open}
            onClose={handleClose}
            fullWidth={true}
            maxWidth='sm'
            aria-labelledby="alert-dialog-title"
            aria-describedby="alert-dialog-description"
         >
            <DialogTitle id="alert-dialog-title" sx={{ textAlign: 'center' }}>
               Sector {currentSectorId} Details
            </DialogTitle>
            <DialogContent>
               {sectorObjects.map(([label, objects], idx) => (
                  <div key={`${label}-${idx}`}>
                     <Divider>{label}</Divider>
                     <List>
                        {objects.map((obj, objIdx) => {
                           const key = isSensor(obj) ? `sensor-${obj.sensorId}` :
                                      isCamera(obj) ? `camera-${obj.cameraId}` :
                                      isForesterPatrol(obj) ? `patrol-${obj.foresterPatrolId}` :
                                      `brigade-${obj.fireBrigadeId}`;
                           return (
                              <ListItem
                                 key={key}
                                 sx={{
                                    height: 1,
                                    cursor: 'pointer',
                                    display: 'inline-flex',
                                    justifyContent: 'space-between',
                                    p: '2px',
                                    borderRadius: '4px',
                                    transition: 'all 0.25s',
                                    '&:hover': {
                                       bgcolor: 'secondary.lighter',
                                    },
                                 }}
                              >
                                 <RenderSimulationItem object={obj} />
                              </ListItem>
                           );
                        })}
                     </List>
                  </div>
               ))}
            </DialogContent>
            <DialogActions>
               <Button onClick={handleClose} variant="contained" color='error'>
                  Close
               </Button>
            </DialogActions>
         </Dialog>
      </>
   );
};

export default DetailsContainer;
