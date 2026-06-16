import { Button } from "@mui/material";
import { useDispatch } from "react-redux";
import { AppDispatch } from "../../store/reduxStore";
import { sendBrigadeOrForesterMoveToBaseOrder } from "../../store/serverCommunicationReducers";
import { useCallback } from "react";

type Props = {
   forestPatrolID: number;
}

export default function ForestPatrolMoveToBaseButton(props: Props) {
   const dispatch: AppDispatch = useDispatch();
   
   const handleClick = useCallback(() => {
      dispatch(sendBrigadeOrForesterMoveToBaseOrder(props.forestPatrolID, "forester"));
   }, [dispatch, props.forestPatrolID]);

   return (
      <Button variant="contained" color="secondary" onClick={handleClick}>Move to Base</Button>
   )
}
