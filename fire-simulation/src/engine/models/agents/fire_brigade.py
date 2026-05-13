import logging
from datetime import datetime
from typing import Optional

from src.engine.models.agents.agent import Agent
from src.engine.models.agents.agent_state import AgentState
from src.engine.models.core.location import Location
from src.engine.models.map.sector import Sector
from src.engine.models.agents.agent_state import AGENT_STATE

logger = logging.getLogger(__name__)

class FireBrigade(Agent):
    """Fire brigade agent - runtime only (no decision logic)"""
    
    def __init__(
        self,
        fire_brigade_id: str,
        timestamp: datetime,
        base_location: Location,
        initial_location: Location,
        initial_state: Optional[AgentState] = None,
    ):
        super().__init__(fire_brigade_id, timestamp, base_location, initial_location)
        self._extinguishing_rate = 5.0  # Increased from 2.0 to 5.0 for faster fire extinguishing  
        
        if initial_state:
            if isinstance(initial_state, AgentState):
                self._state = initial_state
            else:
                match initial_state:
                    case AGENT_STATE.AVAILABLE:
                        self._state = AgentState.IDLE
                    case AGENT_STATE.TRAVELLING:
                        self._state = AgentState.TRAVELING
                    case AGENT_STATE.EXTINGUISHING:
                        self._state = AgentState.EXECUTING
                    case _:
                        logger.warning(f"FireBrigade {self._agent_id}: unknown initial state {initial_state}, defaulting to IDLE")

    def execute_task(self, delta: float, sector: Optional[Sector]) -> bool:
        """Extinguish fire - returns True when sector is clear"""
        if not sector:
            logger.debug(f"FireBrigade {self._agent_id}: no sector resolved, keep executing")
            return False
        
        if sector.fire_level <= 0:
            # Nothing left to extinguish – signal task complete so agent can leave EXECUTING.
            logger.debug(f"FireBrigade {self._agent_id}: sector already clear (fire_level={sector.fire_level:.2f})")
            return True
        
        reduction = self._extinguishing_rate * delta
        sector.fire_level = max(0.0, sector.fire_level - reduction)
        logger.debug(f"FireBrigade {self._agent_id}: fire_level now {sector.fire_level:.2f}")
        
        # Task is complete once fire_level reaches exactly 0.0
        return sector.fire_level <= 0.0
    
    def get_task_progress(self, sector: Optional[Sector]) -> float:
        """Return fire extinguishing progress (0.0 = full fire, 1.0 = extinguished)"""
        if not sector:
            return 1.0
        
        return 1.0 - min(1.0, sector.fire_level)
    
    def can_execute_task(self, sector: Sector) -> bool:
        """Can only extinguish if fire present"""
        return sector.fire_level > 0
    
    def increment_agents_in_sector(self, sector: Sector):
        """No longer used: Map centrally recalculates levels"""
        pass
    
    def decrement_agents_in_sector(self, sector: Sector):
        """No longer used: Map centrally recalculates levels"""
        pass
    
    @property
    def fire_brigade_id(self) -> str:
        return self.agent_id
        
    @property
    def initial_state(self) -> AgentState:
        """Deprecated: Use state instead"""
        return self._state
    
    def clone(self) -> 'FireBrigade':
        """Create a copy of this fire brigade"""

        # Used only for MCTS in support 
        '''
        return FireBrigade(
            fire_brigade_id  = self._agent_id,
            timestamp        = self._timestamp,
            base_location    = Location(self._base_location.latitude, self._base_location.longitude),
            initial_location = Location(self._location.latitude, self._location.longitude),
            initial_state    = self._state
        )
        '''

    def allowed_task_types(self) -> set:
        """FireBrigade accepts movement and extinguish commands (and control commands)."""
        return {"move_to", "extinguish", "return_to_base", "abort"}

    def _handle_executing_state(self, delta: float, map_ref) -> dict:
        """
        FireBrigade-specific handling of EXECUTING state (extinguishing logic,
        logging and agent sector accounting).
        """
        find_sector = map_ref.find_sector if hasattr(map_ref, "find_sector") else None
        current_sector = find_sector(self._location) if find_sector else None
        actual_sec_id = current_sector.sector_id if current_sector else None

        if not self._executing_sector and current_sector:
            self._executing_sector = current_sector
            try:
                self.increment_agents_in_sector(current_sector)
            except Exception:
                pass
            logger.debug(f"[SECTOR-TRACKING] Agent {self._agent_id}: No stored executing_sector, set to current_sector {current_sector.sector_id}")

        if self._executing_sector and current_sector and self._executing_sector.sector_id != current_sector.sector_id:
            current_sector = self._executing_sector
            actual_sec_id  = current_sector.sector_id
        elif current_sector is None and self._executing_sector:
            current_sector = self._executing_sector
            actual_sec_id = current_sector.sector_id

        target_sec_id = None
        if self._current_task and self._current_task.target_sector_id:
            target_sec_id = self._current_task.target_sector_id

        if current_sector is None and target_sec_id and hasattr(map_ref, "get_sector"):
            fallback_sector = map_ref.get_sector(target_sec_id)
            if fallback_sector:
                current_sector = fallback_sector
                actual_sec_id = fallback_sector.sector_id

        old_fire_level = current_sector.fire_level if current_sector else None

        if current_sector:
            logger.debug(f"[TASK] Agent {self._agent_id}: executing task in sector {actual_sec_id} (fire_level: {current_sector.fire_level:.2f}, extinguish_level: {current_sector.extinguish_level})")

        task_complete = self.execute_task(delta, current_sector)

        # Extra safety: if for any reason the sector reference changed or
        # fire_level was clamped to 0 elsewhere, treat it as task complete.
        if current_sector and current_sector.fire_level <= 0.0 and not task_complete:
            logger.debug(f"[EXTINGUISH] Agent {self._agent_id}: fire_level <= 0 detected post-update, forcing task_complete")
            task_complete = True

        if current_sector:
            new_extinguish_level = current_sector.extinguish_level
            if old_fire_level is not None:
                logger.debug(f"[EXTINGUISH] Agent {self._agent_id} in sector {current_sector.sector_id}: fire_level {old_fire_level:.2f} -> {current_sector.fire_level:.2f}")
                logger.debug(f"[SECTOR-DETAIL] Agent {self._agent_id}: actual_sec={actual_sec_id} -> Ext -> target_sec={target_sec_id}, fire_level={current_sector.fire_level:.2f}, extinguish_level={new_extinguish_level}")

        if task_complete:
            # Fire in this sector is out – mark task finished and leave EXECUTING state.
            if self._current_task:
                self._completed_tasks.append(self._current_task)
                self._current_task = None

            if self._executing_sector:
                actual_executing_sec_id = self._executing_sector.sector_id
                self.decrement_agents_in_sector(self._executing_sector)
                logger.debug(f"[EXTINGUISH] Agent {self._agent_id} finished task in sector {actual_executing_sec_id}")
                self._executing_sector = None  # Clear the reference
            
            elif current_sector:
                logger.debug(f"[SECTOR-TRACKING] Agent {self._agent_id}: No stored executing_sector, using current_sector {current_sector.sector_id}")
                self.decrement_agents_in_sector(current_sector)
                logger.debug(f"[EXTINGUISH] Agent {self._agent_id} finished task in sector {current_sector.sector_id}")

            # No auto-return logic here: simply go IDLE. Support will decide what next.
            old_state = self._state.value
            self._state = AgentState.IDLE
            logger.debug(f"[STATE] Agent {self._agent_id}: {old_state} -> idle (task complete, fire out)")

            return {"event": "task_complete", "sector": current_sector, "next_task_started": False}
        else:
            if current_sector and current_sector.fire_level > 0:
                if not hasattr(self, '_task_progress_log_counter'):
                    self._task_progress_log_counter = 0
                self._task_progress_log_counter += 1
                if self._task_progress_log_counter % 20 == 0:
                    logger.debug(f"[TASK] Agent {self._agent_id}: still trying to finish the fire in sector {current_sector.sector_id} - fire_level: {current_sector.fire_level:.2f}, extinguish_level: {current_sector.extinguish_level}")
                logger.debug(f"[EXTINGUISH] Agent {self._agent_id} continuing to extinguish sector {current_sector.sector_id} (fire_level: {current_sector.fire_level:.2f})")
                logger.debug(f"[SECTOR-DETAIL] Agent {self._agent_id}: {actual_sec_id} -> Ext -> {target_sec_id}, fire_level={current_sector.fire_level:.2f}, extinguish_level={current_sector.extinguish_level}")
            elif not current_sector:
                logger.warning(f"[TASK] Agent {self._agent_id}: still trying to finish the fire but not in any sector! Waiting for sector...")
                logger.debug(f"[SECTOR-DETAIL] Agent {self._agent_id}: None -> Ext -> {target_sec_id} [Waiting for sector]")

        return {"event": "executing", "sector": current_sector}

    def _handle_reached_destination(self, current_sector, map_ref, target_sec_id=None, old_state=None) -> dict:
        """
        FireBrigade-specific reached destination handling, preserves previous logging
        and fallback sector resolution.
        """
        if self._destination == self._base_location:
            new_state = AgentState.IDLE
            logger.debug(f"[STATE] Agent {self._agent_id}: {old_state} -> reached base (idle)")
            self._state = new_state
            return {"event": "reached_base", "sector": current_sector}

        actual_id = current_sector.sector_id if current_sector else "None"
        fire_lv = current_sector.fire_level if current_sector else 0.0

        if not current_sector or fire_lv <= 0:
            logger.debug(f"[STATE] Agent {self._agent_id}: {old_state} -> reached sector {actual_id} (fire_level: {fire_lv:.2f}) -> task complete (no fire)")
            if self._current_task:
                self._completed_tasks.append(self._current_task)
                self._current_task = None
            self._state = AgentState.IDLE
            return {"event": "task_complete", "sector": current_sector}

        self._state = AgentState.EXECUTING
        logger.debug(f"[STATE] Agent {self._agent_id}: {old_state} -> reached sector {actual_id} (fire_level: {fire_lv:.2f}) -> executing")

        if current_sector:
            self._executing_sector = current_sector
            try:
                self.increment_agents_in_sector(current_sector)
            except Exception:
                pass
        else:
            resolved_sector = None
            if target_sec_id and hasattr(map_ref, "get_sector"):
                try:
                    resolved_sector = map_ref.get_sector(target_sec_id)
                except Exception:
                    resolved_sector = None
            if resolved_sector:
                logger.warning(f"[EXTINGUISH] Agent {self._agent_id} reached destination but sector lookup failed; using target sector {target_sec_id}.")
                self._executing_sector = resolved_sector
                try:
                    self.increment_agents_in_sector(resolved_sector)
                except Exception:
                    pass
                current_sector = resolved_sector
            else:
                logger.error(f"[EXTINGUISH] Agent {self._agent_id} reached destination location but not in any sector yet. Target sector ID: {target_sec_id}. Location: ({self._location.latitude:.6f}, {self._location.longitude:.6f}). Will try to find sector in next tick.")
        return {"event": "reached_destination", "sector": current_sector}