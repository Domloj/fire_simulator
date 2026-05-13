from abc import ABC, abstractmethod
from datetime import datetime
import logging
import time
import os
import json
from collections import deque
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from src.engine.models.agents.agent_state import AgentState, AGENT_STATE
from src.engine.models.agents.agent_perception import AgentPerception
from src.engine.models.core.location import Location
from src.engine.models.map.sector import Sector

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_prompt_file(filename: str, default: Optional[str] = None) -> Optional[str]:
    try:
        with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return default


_DEFAULT_SYSTEM_PROMPT = (
    "You are Fire Agent {agent_id}. Output requirements:\n"
    "- Return ONLY a single JSON object on the first line and nothing else in that line.\n"
    '- JSON schema: {"observation":"...", "proposition":{"action":"move_to|extinguish|hold","target_sector":null,"reason":"..."}, "narrative":"..."}\n'
)

_DEFAULT_USER_PROMPT = (
    "Context:\n- STATUS: {my_task}\n- RECENT_CHAT: {chat_history}\n- COORDINATOR_FEEDBACK: {coordinator_feedback}\n\n"
    "Task:\nAnalyze the situation and output a valid single-line JSON object (see system prompt).\n"
    "Example JSON (single line): {example_json}\n"
)

STRATEGIC_SYSTEM_PROMPT = _load_prompt_file("strategic_system_prompt.txt", _DEFAULT_SYSTEM_PROMPT)
STRATEGIC_USER_PROMPT_TEMPLATE = _load_prompt_file("strategic_user_prompt.txt", _DEFAULT_USER_PROMPT)


def _safe_format(prompt: Optional[str], **kwargs) -> Optional[str]:
    """Safely replace simple placeholders like {agent_id} without invoking str.format."""
    if prompt is None:
        return None
    result = prompt
    for k, v in kwargs.items():
        result = result.replace(f"{{{k}}}", str(v))
    return result

@dataclass
class AgentTask:
    """Represents a task assigned to an agent"""
    task_type: str 
    target_sector_id: Optional[int] = None
    location: Optional[Location]    = None
    description: str                = ""  # Task description for deduplication
    priority: int                   = 0   # Higher = more important
    timestamp: float                = field(default_factory=time.time)
    command_source: str             = ""  # Where the command came from
    
    def __hash__(self):
        """Hash based on task type and sector ID for deduplication"""
        return hash((self.task_type, self.target_sector_id))
    
    def __eq__(self, other):
        """Equality based on task type and sector ID"""
        if not isinstance(other, AgentTask):
            return False
        return (self.task_type == other.task_type and 
                self.target_sector_id == other.target_sector_id)
    
    def is_similar_to(self, other: 'AgentTask') -> bool:
        """
        Check if tasks are similar (same type and SAME sector).
        Used to detect truly redundant tasks.
        """
        if not isinstance(other, AgentTask):
            return False
        
        if self.task_type != other.task_type:
            return False
        
        if self.target_sector_id == other.target_sector_id:
            return True
        
        return False
    
    def has_more_description_than(self, other: 'AgentTask') -> bool:
        """
        Check if this task has more description than another.
        More description = more specific/important task.
        """

        # Nothing good comes from overcomplicating this logic for now.

        '''
        if not isinstance(other, AgentTask):
            return False
        
        self_desc = self.description.strip().lower()
        other_desc = other.description.strip().lower()
        urgent_keywords = ['urgent', 'critical', 'emergency', 'spreading', 'immediate', 'priority']
        self_has_urgent = any(kw in self_desc for kw in urgent_keywords)
        other_has_urgent = any(kw in other_desc for kw in urgent_keywords)
        
        if self_has_urgent and not other_has_urgent:
            return True
        
        if len(self_desc) > len(other_desc) * 1.5:
            return True
        
        if self.priority > other.priority:
            return True
        '''
        return False

class Agent(ABC):
    """
    Agent runtime - handles physics, movement, state transitions (NOT decisions).
    Decision-making is external (backend/support system).
    """
    _STATE_LABELS = {
        "idle": "Idle",
        "traveling": "Traveling",
        "returning": "Returning",
        "executing": "Extinguishing",
    }
    def __init__(
        self,
        agent_id: str,
        timestamp: datetime,
        base_location: Location,
        initial_location: Location,
    ):
        """Minimal runtime state for all agents; LLM bits are optional and off by default."""
        self._agent_id = agent_id
        self._timestamp = timestamp
        self._base_location = base_location
        self._location = initial_location
        self._destination = base_location
        self._state = AgentState.IDLE

        # Task handling
        self._task_queue: deque = deque()
        self._current_task: Optional[AgentTask] = None
        self._executing_sector: Optional[Sector] = None
        self._completed_tasks: List[AgentTask] = []

        # Optional integration points for LLM / chat reasoning.
        self._communication = None
        self._llm_client = None
        self._last_llm_request_time = 0.0
        self._last_reasoning_time = 0.0
        # Default: agents run WITHOUT LLM chat/reasoning unless explicitly enabled.
        self._llm_chat_enabled = os.environ.get("ENABLE_AGENT_LLM_CHAT", "false").lower() == "true"
        self._llm_cooldown = int(os.environ.get("AGENT_LLM_COOLDOWN_SECONDS", "2"))
        self._reasoning_cooldown = 5.0
            
    def set_communication(self, communication):
        """Optional: set communication adapter used by LLM chat/reasoning."""
        self._communication = communication

    def set_llm_client(self, llm_client):
        """Optional: set LLM client used for reasoning / natural language messages."""
        self._llm_client = llm_client

    def perceive(self, current_sector: Optional[Sector] = None) -> AgentPerception:
        """Gather information about current state (for decision-making)"""

        return AgentPerception(
            current_location        = self._location,
            current_sector          = current_sector,
            executing_sector        = self._executing_sector,
            destination             = self._destination,
            distance_to_destination = self._calculate_distance(self._location, self._destination),
            task_progress           = self.get_task_progress(current_sector) if current_sector else 0.0,
            base_location           = self._base_location
        )
        
    def update_physics(self, delta: float, map_ref) -> Dict[str, Any]:
        """
        Update agent position/state based on physics (called every simulation tick).
        Handles movement, task execution AND (optionally) strategic LLM reasoning.
        """
        # High level reasoning / chat (non-blocking, throttled inside the method)
        # Not all legacy agent subclasses may define strategic reasoning – guard for safety.
        if hasattr(self, "_perform_strategic_reasoning"):
            try:
                self._perform_strategic_reasoning()
            except Exception as e:
                logger.error(f"[LLM] Strategic reasoning failed for agent {self._agent_id}: {e}")
        find_sector = map_ref.find_sector if hasattr(map_ref, "find_sector") else None

        self._process_task_queue(map_ref)

        # SAFETY: if mamy aktywne zadanie z ustawionym celem, ale agent formalnie
        # jest jeszcze w stanie IDLE, wymuś przejście do TRAVELING, żeby ruch się rozpoczął.
        try:
            if (
                self._state == AgentState.IDLE
                and self._current_task is not None
                and self._destination is not None
                and (
                    self._destination.latitude != self._location.latitude
                    or self._destination.longitude != self._location.longitude
                )
            ):
                logger.debug(
                    "[STATE-SAFETY] Agent %s: forcing state idle -> traveling "
                    "because there is an active task and a different destination",
                    self._agent_id,
                )
                self._state = AgentState.TRAVELING
        except Exception:
            # nie blokuj fizyki jeśli coś pójdzie nie tak w powyższej heurystyce
            pass
        
        if self._state in (AgentState.TRAVELING, AgentState.RETURNING):
            old_location   = (self._location.latitude, self._location.longitude)
            old_state      = self._state.value
            reached        = self._move_towards_destination(delta)
            new_location   = (self._location.latitude, self._location.longitude)
            current_sector = find_sector(self._location) if find_sector else None
            actual_sec_id  = current_sector.sector_id if current_sector else None
            target_sec_id  = None

            ''' Get target sector ID from current task or destination '''
            if self._current_task and self._current_task.target_sector_id:
                target_sec_id = self._current_task.target_sector_id
            elif find_sector:
                target_sector = find_sector(self._destination)
                if target_sector:
                    target_sec_id = target_sector.sector_id
            
            ''' Log physics if agent moved or state changed '''
            if old_location != new_location:
                logger.debug(f"[MOVE] Agent {self._agent_id} moved to ({new_location[0]:.6f}, {new_location[1]:.6f}) dest=({self._destination.latitude:.6f}, {self._destination.longitude:.6f}) state={self._state.value}")

                self._physics_log_counter = getattr(self, "_physics_log_counter", 0) + 1
                if self._physics_log_counter % 10 == 0 or self._state.value != old_state:
                    logger.debug(f"[PHYSICS] Agent {self._agent_id} moved from ({old_location[0]:.6f}, {old_location[1]:.6f}) to ({new_location[0]:.6f}, {new_location[1]:.6f}), state: {self._state.value}, actual_sec: {actual_sec_id}, target_sec: {target_sec_id}")
            
            if reached:
                return self._handle_reached_destination(current_sector, map_ref, target_sec_id, old_state)

            return {"event": "moving", "sector": current_sector} 
            
        elif self._state == AgentState.EXECUTING:
            return self._handle_executing_state(delta, map_ref)
        
        return {"event": "idle", "sector": None}

    def _handle_executing_state(self, delta: float, map_ref) -> Dict[str, Any]:
        """
        Generic handler for EXECUTING state.
        Subclasses that implement specific execution logic (e.g. fire brigades)
        should override this method to provide domain-specific behavior.
        Default: call `execute_task` and, if complete, transition to RETURNING.
        """

        find_sector = map_ref.find_sector if hasattr(map_ref, "find_sector") else None
        current_sector = find_sector(self._location) if find_sector else None

        try:
            task_complete = self.execute_task(delta, current_sector)
        except NotImplementedError:
            logger.warning(f"[EXECUTE] Agent {self._agent_id}: execute_task not implemented; switching to IDLE")
            self._state = AgentState.IDLE
            return {"event": "idle", "sector": current_sector}

        if task_complete:
            if self._current_task:
                self._completed_tasks.append(self._current_task)
                self._current_task = None

            self._destination = self._base_location
            self._state = AgentState.RETURNING
            return {"event": "task_complete", "sector": current_sector, "next_task_started": False}
        else:
            return {"event": "executing", "sector": current_sector}

    def _handle_reached_destination(self, current_sector, map_ref, target_sec_id=None, old_state=None) -> Dict[str, Any]:
        """
        Default handler for arriving at the destination. Subclasses can override
        to provide domain-specific behavior (e.g. extinguishing, patrolling).
        """

        if self._destination == self._base_location:
            new_state = AgentState.IDLE
            self._state = new_state
            return {"event": "reached_base", "sector": current_sector}

        if current_sector is None and target_sec_id and hasattr(map_ref, "get_sector"):
            try:
                resolved = map_ref.get_sector(target_sec_id)
                if resolved:
                    current_sector = resolved
            except Exception:
                current_sector = None

        try:
            can_exec = self.can_execute_task(current_sector) if current_sector is not None else False
        except Exception:
            can_exec = False

        if not can_exec:
            if self._current_task:
                self._completed_tasks.append(self._current_task)
                self._current_task = None
            self._state = AgentState.IDLE
            return {"event": "task_complete", "sector": current_sector}

        # Prepare for execution
        self._state = AgentState.EXECUTING
        self._executing_sector = current_sector
        try:
            self.increment_agents_in_sector(current_sector)
        except Exception:
            pass
        return {"event": "reached_destination", "sector": current_sector}

    def _process_task_queue(self, map_ref):
        """
        Process task queue - agents handle their own orders per tick.
        Starts the next queued task when the agent is IDLE or RETURNING.
        """

        # Nothing to do if queue is empty
        if not self._task_queue:
            return

        # Only pick up tasks when idle or returning to base
        if self._state not in (AgentState.IDLE, AgentState.RETURNING):
            return

        try:
            next_task = self._task_queue.popleft()
        except IndexError:
            return

        logger.info(f"[TASK] Agent {self._agent_id} starting queued task: {next_task.task_type} sector:{next_task.target_sector_id} desc:'{next_task.description}'")
        try:
            self._execute_task_internal(next_task, map_ref)
        except Exception as e:
            logger.error(f"[TASK] Agent {self._agent_id} failed to start task {next_task.task_type}: {e}")
            # If failed to start, discard and continue; do not re-queue to avoid infinite loops
            return
    
    def _execute_task_internal(self, task: AgentTask, map_ref):
        """Internal method to execute a task - agents handle their own pathfinding"""
        self._current_task = task
        
        if task.task_type == "move_to" or task.task_type == "extinguish" or task.task_type == "patrol":
            target_location = task.location
            if not target_location and task.target_sector_id and hasattr(map_ref, 'get_sector'):
                try:
                    sector = map_ref.get_sector(task.target_sector_id)
                    if sector and hasattr(map_ref, 'get_sector_location'):
                        target_location = map_ref.get_sector_location(sector)
                except Exception as e:
                    logger.warning(f"[AGENT] {self._agent_id} failed to look up sector {task.target_sector_id}: {e}")
            
            if target_location:
                old_state = self._state.value
                self._destination = target_location
                new_state = AgentState.TRAVELING
                state_map = {"idle": "Idle", "traveling": "Traveling", "returning": "Returning", "executing": "Extinguishing"}
                old_readable = state_map.get(old_state, old_state.title())
                new_readable = state_map.get(new_state.value, new_state.value.title())
                logger.debug(f"[STATE] Agent {self._agent_id}: [{old_readable} -> {new_readable}] [Starting task: {task.task_type} to sector {task.target_sector_id} ({task.description})]")
                self._state = new_state
            else:
                logger.warning(f"[AGENT] {self._agent_id} task {task.task_type} missing location and sector lookup failed")
                
        elif task.task_type == "return_to_base":
            self._destination = self._base_location
            self._state = AgentState.RETURNING
            logger.debug(f"[AGENT] {self._agent_id} returning to base")  # Changed to debug for performance
            
        elif task.task_type == "abort":
            if self._state == AgentState.EXECUTING and self._executing_sector:
                logger.warning(f"[ABORT] Agent {self._agent_id}: Aborting while executing in sector {self._executing_sector.sector_id}")
                self.decrement_agents_in_sector(self._executing_sector)
                self._executing_sector = None
            self._current_task = None
            self._task_queue.clear()
            self._state = AgentState.IDLE
            logger.debug(f"[AGENT] {self._agent_id} task aborted")  # Changed to debug for performance
    
    def _move_towards_destination(self, delta: float) -> bool:
        """Update position, return True if reached destination"""
        movement_speed = 0.001 
        
        movement_delta = movement_speed * delta
        step_lat = self._calculate_step(self._destination.latitude, self._location.latitude, movement_delta)
        step_lon = self._calculate_step(self._destination.longitude, self._location.longitude, movement_delta)
        self._location.latitude += step_lat
        self._location.longitude += step_lon
        
        dist = self._calculate_distance(self._location, self._destination)
        if dist <= 0.00001:  # Small threshold for arrival
            self._location = self._destination  # Snap to exact destination
            return True
        
        return False
    
    def _calculate_step(self, target: float, current: float, delta: float) -> float:
        """Calculate movement step towards target"""
        if target > current:
            return min(delta, target - current)
        elif target < current:
            return max(-delta, target - current)
        return 0.0
    
    def _calculate_distance(self, loc1: Location, loc2: Location) -> float:
        """Calculate Euclidean distance between two locations"""
        return ((loc1.latitude - loc2.latitude)**2 + (loc1.longitude - loc2.longitude)**2)**0.5

    # === LLM REASONING & CHAT INTEGRATION (KEPT) ===========================================

    def _perform_strategic_reasoning(self):
        """Periodically reason and propose changes using Natural Language."""
        if not self._llm_chat_enabled:
            return
        if not self._communication:
            return
        if not self._llm_client:
            return

        current_time = time.time()
        if current_time - self._last_reasoning_time < self._reasoning_cooldown:
            return

        self._last_reasoning_time = current_time

        try:
            announcements = self._communication.get_recent_announcements(max_count=20)
            coordinator_responses = self._communication.get_coordinator_responses(max_count=5)
            chat_history = [
                f"{a.get('agent_id', 'Unknown')}: {a.get('description')}"
                for a in announcements
                if a.get("description")
            ]

            coordinator_feedback = []
            for resp in coordinator_responses:
                content = resp.get("content", {})
                if isinstance(content, dict):
                    prop_text = content.get("proposition", "")
                    if prop_text:
                        coordinator_feedback.append(f"Coordinator: {prop_text}")

            my_task = (
                f"{self._current_task.task_type} in sector {self._current_task.target_sector_id}"
                if self._current_task
                else "idle"
            )

            system_prompt = _safe_format(STRATEGIC_SYSTEM_PROMPT, agent_id=self._agent_id) or _safe_format(
                _DEFAULT_SYSTEM_PROMPT, agent_id=self._agent_id
            )
            example_json = json.dumps(
                {
                    "observation": "Sector 8 unattended, high fire level",
                    "proposition": {
                        "action": "move_to",
                        "target_sector": 8,
                        "reason": "Reduce spread",
                    },
                    "narrative": "I feel we should hurry!",
                },
                ensure_ascii=False,
            )

            user_prompt = _safe_format(
                STRATEGIC_USER_PROMPT_TEMPLATE,
                my_task=my_task,
                chat_history=(chr(10).join(chat_history) if chat_history else "None"),
                coordinator_feedback=(chr(10).join(coordinator_feedback) if coordinator_feedback else "None"),
                example_json=example_json,
            ) or _safe_format(
                _DEFAULT_USER_PROMPT,
                my_task=my_task,
                chat_history=(chr(10).join(chat_history) if chat_history else "None"),
                coordinator_feedback=(chr(10).join(coordinator_feedback) if coordinator_feedback else "None"),
                example_json=example_json,
            )

            def _extract_json_and_narrative(resp_text: str):
                start = resp_text.find("{")
                end = resp_text.rfind("}")
                if start == -1 or end == -1 or end < start:
                    return None, None
                json_text = resp_text[start : end + 1]
                narrative = None
                if "---" in resp_text:
                    parts = resp_text.split("---", 1)
                    tail = parts[1].strip()
                    if tail:
                        narrative = tail.splitlines()[0].strip()
                else:
                    tail = resp_text[end + 1 :].strip()
                    if tail:
                        narrative = tail.splitlines()[0].strip()
                try:
                    return json.loads(json_text), narrative
                except Exception:
                    return None, narrative

            response = self._llm_client.complete(user_prompt, system_prompt)
            data, narrative_tail = _extract_json_and_narrative(response)
            if data is None:
                retry_prompt = (
                    "Previous output was not valid JSON according to the schema. "
                    "Return ONLY a single-line JSON object as described.\n" + user_prompt
                )
                response2 = self._llm_client.complete(retry_prompt, system_prompt)
                data, narrative_tail = _extract_json_and_narrative(response2)

            observation = None
            proposition = None
            narrative = None

            if isinstance(data, dict):
                observation = data.get("observation")
                proposition = data.get("proposition")
                narrative = data.get("narrative") or narrative_tail

            chat_description = observation if observation else (narrative or "No observation")
            if narrative and observation:
                chat_description = f"{observation} — {narrative}"

            try:
                chat_msg = {
                    "agentId": self._agent_id,
                    "type": "AgentReasoning",
                    "description": chat_description,
                    "timestamp": datetime.now().isoformat(),
                }
                if hasattr(self._communication, "announce_to_llm_chat"):
                    self._communication.announce_to_llm_chat(chat_msg)
            except Exception:
                logger.exception("Failed to announce agent reasoning chat message")

            prop_str = None
            if isinstance(proposition, dict):
                action = proposition.get("action", "hold")
                target = proposition.get("target_sector")
                reason = proposition.get("reason", "")
                if target is not None:
                    prop_str = f"{action} -> sector {target}: {reason}"
                else:
                    prop_str = f"{action}: {reason}"
            elif isinstance(proposition, str):
                prop_str = proposition

            if prop_str:
                try:
                    if hasattr(self._communication, "send_proposition_to_coordinator"):
                        self._communication.send_proposition_to_coordinator(self._agent_id, prop_str)
                    else:
                        prop_msg = {
                            "agentId": self._agent_id,
                            "type": "AgentProposition",
                            "description": prop_str,
                            "timestamp": datetime.now().isoformat(),
                        }
                        if hasattr(self._communication, "_message_store"):
                            self._communication._message_store.add_message_to_sent(
                                "support.llm.propositions", prop_msg
                            )
                except Exception:
                    logger.exception("Failed to send proposition to coordinator")

        except Exception as e:
            logger.error(f"[AGENT-REASON] LLM reasoning failed for {self._agent_id}: {e}")

    def _announce_to_chat(self, description: str, type: str = "BrigadeOrder"):
        """Helper to send a natural language message to the strategic chat."""
        if not self._communication:
            return
        try:
            msg = {
                "agentId": self._agent_id,
                "type": type,
                "description": description,
                "timestamp": datetime.now().isoformat(),
                "status": self._state.value,
                "sectorId": self._executing_sector.sector_id if self._executing_sector else None,
            }
            if hasattr(self._communication, "announce_to_llm_chat"):
                self._communication.announce_to_llm_chat(msg)
        except Exception as e:
            logger.error(f"[AGENT-CHAT] Chat announcement failed: {e}")

    def _announce_order_to_llm(self, task: AgentTask):
        """Announce new order using Natural Language generated by LLM."""
        if not self._communication:
            return
        if not self._llm_client:
            return
        current_time = time.time()
        if current_time - self._last_llm_request_time < self._llm_cooldown:
            return

        try:
            action_type = "move_to" if task.task_type == "move_to" else "extinguish"
            sector_info = (
                f"sector {task.target_sector_id}"
                if task.target_sector_id is not None
                else "unknown location"
            )

            if task.description:
                context_why = f"Reason: {task.description}"
            else:
                if action_type == "extinguish":
                    context_why = "Reason: Fire detected and requires immediate extinguishing"
                else:
                    context_why = "Reason: Moving to optimal tactical position"

            announce_system = _load_prompt_file("announce_system_prompt.txt", None)
            announce_user = _load_prompt_file("announce_user_prompt.txt", None)

            system_prompt = _safe_format(announce_system, agent_id=self._agent_id) if announce_system else (
                f"You are Fire Brigade Agent {self._agent_id}. Generate a DETAILED, NATURAL language message "
                "announcing your current action.\n- Keep it short (<=25 words)\n- Output ONLY a single line message"
            )

            user_prompt = _safe_format(
                announce_user,
                action_type=action_type,
                sector_info=sector_info,
                status=self._state.value,
                context_why=context_why,
            ) if announce_user else (
                f"Action: {action_type}\nTarget: {sector_info}\nStatus: {self._state.value}\n{context_why}"
            )

            nl_resp = self._llm_client.complete(user_prompt, system_prompt).strip()
            nl_line = nl_resp.splitlines()[0].strip() if nl_resp else ""

            if not nl_line:
                retry_system = (announce_system or system_prompt) + "\nOutput only one short line (<=25 words)."
                retry_user = (announce_user or user_prompt) + "\nReturn a single short line now."
                nl_resp2 = self._llm_client.complete(retry_user, retry_system).strip()
                nl_line = nl_resp2.splitlines()[0].strip() if nl_resp2 else ""

            if nl_line and len(nl_line.split()) > 25:
                nl_line = " ".join(nl_line.split()[:25])

            nl_msg = nl_line
            action_label = "[move]" if task.task_type == "move_to" else "[extinguish]"
            sector_label = (
                f"[sector {task.target_sector_id}]" if task.target_sector_id is not None else "[moving]"
            )

            order_message = {
                "agentId": self._agent_id,
                "type": "BrigadeOrder",
                "description": f"{nl_msg} {action_label} {sector_label}",
                "timestamp": datetime.now().isoformat(),
                "status": self._state.value,
                "sectorId": task.target_sector_id,
            }

            if hasattr(self._communication, "announce_to_llm_chat"):
                self._communication.announce_to_llm_chat(order_message)
                self._last_llm_request_time = current_time
                logger.debug(f"[AGENT-CHAT] {self._agent_id} announced: {nl_msg}")
        except Exception as e:
            logger.error(f"[AGENT-CHAT] Failed to announce order for {self._agent_id}: {e}")
    
    def _generate_status_announcement(self, current_sector: Optional[Sector] = None) -> Optional[Dict[str, Any]]:
        """
        Generate a natural language status announcement with sector and status info.
        Called every second to publish agent status updates.
        
        ALWAYS WORKS - uses LLM if available, otherwise uses template-based generation with randomization.
        Messages always vary to avoid mocking/static content.
        
        Returns announcement dict with natural_language, sector, status, and location.
        """
        if not self._communication:
            return None
        
        # Throttle to once per second
        current_time = time.time()
        if not hasattr(self, '_last_status_announcement_time'):
            self._last_status_announcement_time = 0.0
        
        if current_time - self._last_status_announcement_time < 1.0:
            return None
        
        try:
            # Get current sector ID
            sector_id = current_sector.sector_id if current_sector else None
            
            # Map state to readable status
            status_map = {
                "idle": "AVAILABLE",
                "traveling": "TRAVELLING",
                "executing": "EXTINGUISHING" if hasattr(self, 'fire_brigade_id') else "PATROLLING",
                "returning": "TRAVELLING"
            }
            status = status_map.get(self._state.value, "AVAILABLE")
            
            # Generate natural language - try LLM first, fallback to templates
            nl_response = None
            
            if self._llm_client:
                # Use LLM for varied, natural language (with shorter prompt for speed)
                try:
                    import random
                    # Shorter, faster prompt
                    action_description = "ready" if status == "AVAILABLE" else \
                                       "moving" if status == "TRAVELLING" else \
                                       "fighting fires" if status == "EXTINGUISHING" else \
                                       "patrolling" if status == "PATROLLING" else \
                                       "returning"
                    
                    user_prompt = (
                        f"Agent {self._agent_id}: status={status}, action={action_description}, "
                        f"sector={sector_id or 'unknown'}. "
                        f"Brief status update, max 20 words. Format: 'Hey, Agent {self._agent_id}, my status is {status}, I'm {action_description}, {{SECTOR: {sector_id}, STATUS: {status}}}'"
                    )
                    
                    # Use shorter system prompt for faster response
                    system_prompt = "You are a fire agent. Generate brief status updates. Keep responses under 20 words."
                    
                    nl_response = self._llm_client.complete(user_prompt, system_prompt).strip()
                    # Validate response isn't too long or empty
                    if not nl_response or len(nl_response) > 200:
                        nl_response = None  # Fall back to template if empty or too long
                except Exception as e:
                    # LLM failures are expected (timeouts, network issues) - use debug level
                    logger.debug(f"[AGENT-STATUS] LLM generation failed for {self._agent_id}, using template: {type(e).__name__}")
                    nl_response = None
            
            # Fallback to template-based generation (ALWAYS VARIES)
            if not nl_response:
                import random
                
                # Template variations for each status - ensures messages vary
                templates = {
                    "AVAILABLE": [
                        "Hey, Agent {agent_id}, I'm {agent_id} and I'm ready to respond to fires",
                        "Agent {agent_id} here, status is AVAILABLE and ready for action",
                        "This is {agent_id}, I'm available and waiting for orders",
                        "{agent_id} reporting in, ready to deploy when needed"
                    ],
                    "TRAVELLING": [
                        "Hey, Agent {agent_id}, I'm currently moving to my destination",
                        "Agent {agent_id} en route, traveling to assigned location",
                        "This is {agent_id}, I'm on the move to my target",
                        "{agent_id} here, currently traveling to the scene"
                    ],
                    "EXTINGUISHING": [
                        "Hey, Agent {agent_id}, I'm actively extinguishing a fire",
                        "Agent {agent_id} engaged in firefighting operations",
                        "This is {agent_id}, currently fighting fires",
                        "{agent_id} reporting, fire suppression in progress"
                    ],
                    "PATROLLING": [
                        "Hey, Agent {agent_id}, I'm patrolling my assigned area",
                        "Agent {agent_id} on patrol duty, monitoring the sector",
                        "This is {agent_id}, conducting routine patrol",
                        "{agent_id} here, patrolling and watching for issues"
                    ]
                }
                
                # Select random template for variation
                template_list = templates.get(status, templates["AVAILABLE"])
                base_message = random.choice(template_list).format(agent_id=self._agent_id)
                
                # Add sector info if available
                if sector_id is not None:
                    sector_variations = [
                        f" in sector {sector_id}",
                        f", currently in sector {sector_id}",
                        f", sector {sector_id}",
                        f" at sector {sector_id}"
                    ]
                    base_message += random.choice(sector_variations)
                
                nl_response = f"{base_message}, {{SECTOR: {sector_id}, STATUS: {status}}}"
            
            # Ensure the contracts format is included
            if "{SECTOR:" not in nl_response and sector_id is not None:
                nl_response += f", {{SECTOR: {sector_id}, STATUS: {status}}}"
            
            announcement = {
                "timestamp": datetime.now().isoformat(),
                "agent_id": self._agent_id,
                "natural_language": nl_response,
                "sector": sector_id,
                "status": status,
                "location": {
                    "latitude": self._location.latitude,
                    "longitude": self._location.longitude
                }
            }
            
            self._last_status_announcement_time = current_time
            return announcement
            
        except Exception as e:
            logger.error(f"[AGENT-STATUS] Failed to generate status announcement for {self._agent_id}: {e}", exc_info=True)
            return None
    
    def execute_command(self, command: Dict[str, Any]):
        """
        Add command to task queue - agents handle their own orders.
        Implements deduplication: ignores redundant tasks unless they have more description.
        """
        cmd_type       = command.get("type")
        description    = command.get("description", "")
        priority       = command.get("priority", 0)
        sector_id      = command.get("sectorId") or command.get("target_sector_id")
        command_source = command.get("source", "unknown")

        is_override = False
        if self._state == AgentState.EXECUTING:
            if priority < 10:
                logger.info(f"[TASK-LOCK] Agent {self._agent_id} is busy {self._state.value} in sector {self._executing_sector.sector_id if self._executing_sector else 'unknown'}. "
                           f"Ignoring low-priority command: {cmd_type} (priority: {priority})")
                return
            else:
                logger.warning(f"[TASK-OVERRIDE] Agent {self._agent_id} task override! "
                             f"High-priority command {cmd_type} (priority: {priority}) from {command_source}")
                is_override = True
        
        logger.info(f"[AGENT-RECV] {self._agent_id} received command: {cmd_type}, sector: {sector_id}, desc: '{description}', source: {command_source}")
        
        # Validate command type for this agent
        try:
            allowed = self.allowed_task_types()
        except Exception:
            allowed = {"move_to", "extinguish", "patrol", "return_to_base", "abort"}
        if cmd_type not in allowed:
            logger.warning(f"[AGENT] {self._agent_id} cannot accept command type '{cmd_type}'; allowed: {sorted(list(allowed))}")
            return

        task = None
        loc_data = command.get("location", {})
        target = Location(loc_data.get("latitude"), loc_data.get("longitude")) if loc_data else None

        match cmd_type:
            case "move_to":
                if not loc_data or not target:
                    logger.error(f"[AGENT] {self._agent_id} move_to command missing location: {command}")
                    return
                
                task = AgentTask(
                    task_type        = "move_to",
                    target_sector_id = sector_id,
                    location         = target,
                    description      = description,
                    priority         = priority,
                    command_source   = command_source
                )

            case "extinguish":
                if not loc_data or not target:
                    logger.error(f"[AGENT] {self._agent_id} extinguish command missing location: {command}")
                    return
                
                task = AgentTask(
                    task_type        = "extinguish",
                    target_sector_id = sector_id,
                    location         = target,
                    description      = description,
                    priority         = priority,
                    command_source   = command_source
                )

            case "patrol":
                if not loc_data or not target:
                    logger.error(f"[AGENT] {self._agent_id} patrol command missing location: {command}")
                    return
                
                task = AgentTask(
                    task_type        = "patrol",
                    target_sector_id = sector_id,
                    location         = target,
                    description      = description,
                    priority         = priority,
                    command_source   = command_source
            )
                
            case "return_to_base":
                task = AgentTask(
                    task_type        = "return_to_base",
                    description      = description,
                    priority         = priority,
                    command_source   = command_source
                )
        
            case "abort":
                task = AgentTask(
                    task_type        = "abort",
                    description      = description,
                    priority         = priority,
                    command_source   = command_source
                )

            case _:
                logger.error(f"[AGENT] {self._agent_id} received unknown command type: {cmd_type}")
                return
        
        if not task:
            return
            
        # New behavior: handle commands immediately (no queuing safety). For tactical commands
        # (move_to, extinguish, patrol, return_to_base) we interrupt current task, clear the queue,
        # and schedule the new task at the front so it starts on the next physics tick.
        if self._should_ignore_task(task):
            # logger.debug(f"[AGENT] {self._agent_id} ignoring redundant task: {task.task_type} "
            #            f"sector {task.target_sector_id} ('{task.description}') - "
            #            f"similar task already in queue or being executed")
            return

        immediate_types = {"move_to", "extinguish", "patrol", "return_to_base"}
        if task.task_type in immediate_types:
            logger.info(f"[TASK-IMMEDIATE] Agent {self._agent_id} scheduling IMMEDIATE task: {task.task_type} sector:{task.target_sector_id} desc:'{task.description}' source:{task.command_source}")

            # If currently executing, decrement sector counters and clear executing sector
            if self._executing_sector:
                try:
                    self.decrement_agents_in_sector(self._executing_sector)
                except Exception:
                    pass
                self._executing_sector = None

            # Clear any existing queued tasks and place this one at the front
            try:
                self._task_queue.clear()
            except Exception:
                pass
            self._task_queue.appendleft(task)

            # Force agent into IDLE so _process_task_queue will start this task immediately
            self._state = AgentState.IDLE

            logger.debug(f"[TASK-IMMEDIATE] Agent {self._agent_id} will start {task.task_type} on next tick")

            # Announce task to LLM Chat if enabled
            if self._llm_chat_enabled:
                self._announce_order_to_llm(task)
            return

        # Default behavior (should still rarely be used): add to queue
        self._add_task_to_queue(task)

        logger.info(f"[AGENT] {self._agent_id} added task to queue: {task.task_type} "
                   f"sector {task.target_sector_id} ('{task.description}'), "
                   f"queue size: {len(self._task_queue)}")
        
        # Announce task to LLM Chat if enabled
        if self._llm_chat_enabled:
            self._announce_order_to_llm(task)
    
    def _should_ignore_task(self, new_task: AgentTask) -> bool:
        """
        Check if task should be ignored due to redundancy, or replace existing tasks
        when the new task is clearly better (more descriptive or higher priority).

        Behavior:
        - If identical task exists as current or queued -> ignore
        - If similar task exists:
          - If new task has more description OR higher priority -> replace existing task
          - Otherwise -> ignore
        - Special-case: while EXECUTING, only explicit high-priority overrides are allowed
          (handled in execute_command). We avoid mutating the executing task here.
        """

        # OLD LOGIC - IGNORE - LEAVE FOR REFERENCE

        # if self._current_task:
        #     if self._current_task == new_task:
        #         return True

        #     if self._current_task.is_similar_to(new_task):
        #         if self._state == AgentState.EXECUTING:
        #             return False

        #         if new_task.has_more_description_than(self._current_task) or new_task.priority > self._current_task.priority:
        #             old = self._current_task
        #             self._current_task = None
        #             try:
        #                 self._task_queue.appendleft(old)
        #             except Exception:
        #                 pass
        #             logger.info(f"[AGENT] {self._agent_id} replacing current task with higher-priority/better task: {old.task_type} -> {new_task.task_type}")
        #             return False

        #         return True

        # for queued_task in list(self._task_queue):
        #     if queued_task == new_task:
        #         return True

        #     if queued_task.is_similar_to(new_task):
        #         if new_task.has_more_description_than(queued_task) or new_task.priority > queued_task.priority:
        #             try:
        #                 self._task_queue.remove(queued_task)
        #             except ValueError:
        #                 pass
        #             logger.info(f"[AGENT] {self._agent_id} replacing queued task with better one: {queued_task.description} -> {new_task.description}")
        #             return False
        #         return True

        return False
    
    def _add_task_to_queue(self, task: AgentTask):
        """Add task to queue, maintaining priority order"""
        if not self._task_queue:
            self._task_queue.append(task)
            return
        
        inserted = False
        for i, queued_task in enumerate(self._task_queue):
            if task.priority > queued_task.priority:
                self._task_queue.insert(i, task)
                inserted = True
                break
        
        if not inserted:
            self._task_queue.append(task)
        
    def allowed_task_types(self) -> set:
        """Return set of allowed command types for this agent. Subclasses should override if needed."""
        return {"move_to", "extinguish", "patrol", "return_to_base", "abort"}

    @abstractmethod
    def execute_task(self, delta: float, sector: Optional[Sector]) -> bool:
        """Execute agent-specific task, return True when complete"""
        pass
    
    @abstractmethod
    def get_task_progress(self, sector: Optional[Sector]) -> float:
        """Return task completion (0.0 - 1.0)"""
        pass
    
    @abstractmethod
    def can_execute_task(self, sector: Sector) -> bool:
        """Check if agent can perform task in given sector"""
        pass
    
    @abstractmethod
    def increment_agents_in_sector(self, sector: Sector):
        """Increment agent counter in sector (for tracking)"""
        pass
    
    @abstractmethod
    def decrement_agents_in_sector(self, sector: Sector):
        """Decrement agent counter in sector (for tracking)"""
        pass
        
    @property
    def agent_id(self) -> str:
        return self._agent_id
    
    @property
    def state(self) -> AgentState:
        return self._state
    
    @property
    def location(self) -> Location:
        return self._location
    
    @property
    def destination(self) -> Location:
        return self._destination
    
    @property
    def base_location(self) -> Location:
        return self._base_location
    
    @property
    def timestamp(self) -> datetime:
        return self._timestamp
