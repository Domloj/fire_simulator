package pl.edu.agh.kis.firebackend.model.primitives;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public record Location(
    @JsonProperty("longitude") float longitude,
    @JsonProperty("latitude") float latitude
) {
    @JsonCreator
    public Location(
            @JsonProperty("longitude") float longitude,
            @JsonProperty("latitude") float latitude
    ) {
        this.longitude = longitude;
        this.latitude = latitude;
    }
}
