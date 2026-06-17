package pl.edu.agh.kis.firebackend.service.model.frontend;

import com.fasterxml.jackson.annotation.JsonProperty;
import pl.edu.agh.kis.firebackend.model.primitives.Location;

public class FrontOrderPatrol extends FrontOrder {

    @JsonProperty("foresterPatrolId")
    private int foresterPatrolId;

    public FrontOrderPatrol(int foresterPatrolId, Location location, boolean isGoToBase){
        super(location, isGoToBase);
        this.foresterPatrolId = foresterPatrolId;
    }


    public int getId(){
        return foresterPatrolId;
    }

    @Override
    public String toString() {
        return "FrontOrderPatrol{" +
                "foresterPatrolId=" + foresterPatrolId +
                ", location=" + getLocation() +
                ", isGoToBase=" + isGoToBase() +
                ", source=" + getSource() +
                '}';
    }
    
}
