package pl.edu.agh.kis.firebackend.service.model.frontend;

import pl.edu.agh.kis.firebackend.model.primitives.Location;;

public abstract class FrontOrder 
{
    private Location location;
    private boolean isGoToBase;
    // Optional origin marker inserted by clients (e.g., 'manual' or 'auto')
    private String source;

    public FrontOrder(Location location, boolean isGoToBase) {
        this.location = location;
        this.isGoToBase = isGoToBase;
    }
    public abstract int getId();

    public Location getLocation()
    {
        return location;
    };

    public boolean isGoToBase()
    {
        return isGoToBase;
    };

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }
}
