package pl.edu.agh.kis.firebackend.service.model;

public record UpdatesQueue<T>(String name, Class<T> eventClass) 
{

}
