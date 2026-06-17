import { Box, Button, Divider, List, ListItem, Typography } from "@mui/material";
import RenderSimulationItem from "./RenderSimulationItem";
import { FireBrigade } from "../../model/FireBrigade";
import { useSelector } from "react-redux";
import { RootState } from "../../store/reduxStore";
import { useMemo } from "react";
import { getObjectsInSector } from '@shared/utils/getObjectsInSector';

export default function FireBrigadeManagement() {
   const {
      configuration: mapConfiguration,
      currentSectorId,
   } = useSelector((state: RootState) => state.mapConfiguration);

   const filteredBrigades = useMemo(() => {
      if (currentSectorId === null) {
         return [];
      }
      return getObjectsInSector(mapConfiguration.sectors[currentSectorId - 1], mapConfiguration.fireBrigades);
   }, [mapConfiguration.sectors, mapConfiguration.fireBrigades, currentSectorId]);

   if (currentSectorId === null) {
      return null;
   }

   return (
      <Box>
         <Divider><Typography variant="h2">Fire Brigades</Typography></Divider>
         <List>
            {filteredBrigades.map((obj, ind) => (
               <ListItem
                  sx={{
                     height: 1,
                     cursor: 'pointer',
                     display: 'inline-flex',
                     justifyContent: 'space-between',
                     p: '2px',
                     borderRadius: '4px',
                     transition: 'all 0.25s',
                     width: '500px',
                     '&:hover': {
                        bgcolor: 'secondary.lighter',
                     },
                  }}
                  key={`fire-brigade-${obj.fireBrigadeId}-${ind}`}
               >
                  <RenderSimulationItem object={obj} />
               </ListItem>
            ))}
         </List>
      </Box>
   )
}
