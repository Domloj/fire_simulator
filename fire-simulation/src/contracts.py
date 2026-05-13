# Common data structures and contracts
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class AgentStateDTO:
    agent_id: str
    state: str
    location: dict
    sector_id: Optional[int]
    timestamp: str
