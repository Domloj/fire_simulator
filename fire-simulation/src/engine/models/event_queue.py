"""
Event queue for fire simulation.

Separates event generation from event application for:
- Deterministic ordering
- Replay capability
- Easier debugging
- Audit trail
"""

from enum import Enum
from typing import List, Dict, Any
from dataclasses import dataclass


class EventType(Enum):
    """Event types in simulation."""
    
    IGNITION = "IGNITION"                      # Sector caught fire
    BURNOUT = "BURNOUT"                        # Fuel depleted -> ASH
    EXTINGUISHMENT = "EXTINGUISHMENT"          # Extinguished -> ASH
    FUEL_UPDATE = "FUEL_UPDATE"                # Fuel consumed
    BURN_LEVEL_UPDATE = "BURN_LEVEL_UPDATE"    # Cumulative burn tracked
    FIRE_LEVEL_UPDATE = "FIRE_LEVEL_UPDATE"    # Fire intensity changed


@dataclass
class SimulationEvent:
    """Single event in simulation tick."""
    
    tick: int
    event_type: EventType
    sector_id: int
    
    # Event-specific data
    old_value: float = None
    new_value: float = None
    
    def __repr__(self) -> str:
        return (f"Event(tick={self.tick}, type={self.event_type.value}, "
                f"sector={self.sector_id}, {self.old_value}->{self.new_value})")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "tick": self.tick,
            "type": self.event_type.value,
            "sector_id": self.sector_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


class EventQueue:
    """Event queue for tick."""
    
    def __init__(self):
        """Initialize empty event queue."""
        self.events: List[SimulationEvent] = []
    
    def add_event(self, 
                  tick: int,
                  event_type: EventType,
                  sector_id: int,
                  old_value: float = None,
                  new_value: float = None) -> None:
        """Add event to queue."""
        event = SimulationEvent(
            tick=tick,
            event_type=event_type,
            sector_id=sector_id,
            old_value=old_value,
            new_value=new_value,
        )
        self.events.append(event)
    
    def get_events_by_type(self, event_type: EventType) -> List[SimulationEvent]:
        """Get all events of specific type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_for_sector(self, sector_id: int) -> List[SimulationEvent]:
        """Get all events for specific sector."""
        return [e for e in self.events if e.sector_id == sector_id]
    
    def get_ignition_events(self) -> List[SimulationEvent]:
        """Get all ignition events."""
        return self.get_events_by_type(EventType.IGNITION)
    
    def get_burnout_events(self) -> List[SimulationEvent]:
        """Get all burnout events."""
        return self.get_events_by_type(EventType.BURNOUT)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert queue to dictionary for logging."""
        return {
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events]
        }
    
    def __repr__(self) -> str:
        return f"EventQueue({len(self.events)} events)"
    
    def __len__(self) -> int:
        return len(self.events)
