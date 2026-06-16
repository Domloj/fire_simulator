import { Box, Button, Divider, List, ListItem, Typography } from "@mui/material";
import RenderSimulationItem from "./RenderSimulationItem";
import { useSelector } from "react-redux";
import { RootState } from "../../store/reduxStore";
import { useMemo } from "react";
import { getObjectsInSector } from '@shared/utils/getObjectsInSector';

export default function ForestPatrolManagement() {
   const {
      configuration: mapConfiguration,
      currentSectorId,
   } = useSelector((state: RootState) => state.mapConfiguration);

   const forestPatrols = useMemo(() => {
      if (currentSectorId === null) {
         return [];
      }
      return getObjectsInSector(mapConfiguration.sectors[currentSectorId - 1], mapConfiguration.foresterPatrols);
   }, [mapConfiguration.sectors, mapConfiguration.foresterPatrols, currentSectorId]);

   if (currentSectorId === null) {
      return null;
   }

   return (
      <Box>
         <Divider><Typography variant="h2">Forest Patrols</Typography></Divider>
         <List>
            {forestPatrols.map((obj, ind) => (
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
                  key={`forest-patrol-${obj.foresterPatrolId}-${ind}`}
               >
                  <RenderSimulationItem object={obj} />
               </ListItem>
            ))}
         </List>        
      </Box>
   )
}
