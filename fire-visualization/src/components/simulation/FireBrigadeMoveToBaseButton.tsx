import { Button } from "@mui/material";
import { useDispatch } from "react-redux";
import { AppDispatch } from "../../store/reduxStore";
import { sendBrigadeOrForesterMoveToBaseOrder } from "../../store/serverCommunicationReducers";
import { useCallback } from "react";

type Props = {
   fireBrigadeID: number;
}

export default function FireBrigadeMoveToBaseButton(props: Props) {
   const dispatch: AppDispatch = useDispatch();
   
   const handleClick = useCallback(() => {
      dispatch(sendBrigadeOrForesterMoveToBaseOrder(props.fireBrigadeID, "brigade"));
   }, [dispatch, props.fireBrigadeID]);

   return (
      <Button variant="contained" color="secondary" onClick={handleClick}>Move to Base</Button>
   )
}
