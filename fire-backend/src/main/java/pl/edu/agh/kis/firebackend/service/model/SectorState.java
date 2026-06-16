package pl.edu.agh.kis.firebackend.service.model;

import lombok.AllArgsConstructor;
import pl.edu.agh.kis.firebackend.model.primitives.Direction;

import java.util.Date;

public class SectorState 
{
    public Date timestamp;
    public double temperature;
    public double windSpeed;
    public Direction windDirection;
    public double airHumidity;
    public double plantLitterMoisture;
    public double co2Concentration;
    public double pm2_5Concentration;
    public ThreatLevel threatLevel;
    public FireState fireState;

    // For debugging purposes
    public double fireLevel;
    public double burnLevel; 
    public double extinguishLevel;

    public SectorState(Date timestamp, double temperature, double windSpeed, Direction windDirection, double airHumidity, double plantLitterMoisture, double co2Concentration, double pm2_5Concentration, ThreatLevel threatLevel, FireState fireState, double fireLevel, double burnLevel, double extinguishLevel) {
        this.timestamp = timestamp;
        this.temperature = temperature;
        this.windSpeed = windSpeed;
        this.windDirection = windDirection;
        this.airHumidity = airHumidity;
        this.plantLitterMoisture = plantLitterMoisture;
        this.co2Concentration = co2Concentration;
        this.pm2_5Concentration = pm2_5Concentration;
        this.threatLevel = threatLevel;
        this.fireState = fireState;
        this.fireLevel = fireLevel;
        this.burnLevel = burnLevel;
        this.extinguishLevel = extinguishLevel;
    }
}
