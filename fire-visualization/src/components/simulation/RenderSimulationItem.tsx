import { Button, Typography } from "@mui/material";
import { ReactNode, memo } from "react";
import { Camera, isCamera } from "../../model/camera";
import { FireBrigade } from "../../model/FireBrigade";
import { ForesterPatrol, isForesterPatrol } from "../../model/ForesterPatrol";
import { Sensor, isSensor } from "../../model/sensor";
import FireBrigadeDialog from "./FireBrigadeDialog";
import FireBrigadeMoveToBaseButton from "./FireBrigadeMoveToBaseButton";
import ForestPatrolMoveToBaseButton from "./ForestPatrolMoveToBaseButton";
import ForestPatrolDialog from "./ForestPatrolDialog";

type Props = {
   object: Sensor | Camera | FireBrigade | ForesterPatrol;  
}

function RenderSimulationItem({object}: Props): ReactNode {
   if (isSensor(object)) {
      return (
         <>
            <Typography sx={{ width: 50 }}>ID: {object.sensorId}</Typography>
            <Typography>Type: {object.sensorType}</Typography>
         </>
      );
   } else if (isCamera(object)) {
      return (
         <>
            <Typography sx={{ width: 50 }}>ID: {object.cameraId}</Typography>
            <Typography>Range: {object.range}</Typography>
         </>
      );
   } else if (isForesterPatrol(object)) {
      return (
         <>
            <Typography sx={{ width: 50 }}>ID: {object.foresterPatrolId}</Typography>
            <Typography>State: {object.state}</Typography>
            <ForestPatrolMoveToBaseButton forestPatrolID={object.foresterPatrolId}/>
            <ForestPatrolDialog forestPatrolID={object.foresterPatrolId} />
         </>
      );
   } else {
      return (
         <>
            <Typography sx={{ width: 50 }}>ID: {object.fireBrigadeId}</Typography>
            <Typography>State: {object.state}</Typography>            
            <FireBrigadeMoveToBaseButton fireBrigadeID={object.fireBrigadeId}/>
            <FireBrigadeDialog fireBrigadeID={object.fireBrigadeId} />
         </>
      );
   }
}

export default memo(RenderSimulationItem);
