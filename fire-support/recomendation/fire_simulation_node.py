import collections
import copy
import heapq
import random
import numpy as np

from collections import defaultdict, namedtuple
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import permutations, product
from typing import Any, Dict, FrozenSet, List, NamedTuple, Optional, Set, Tuple

from recomendation.reward_calculator import RewardCalculator
from recomendation.node import Node

from simulation.agent import Agent
from simulation.agent_state import AGENT_STATE
from simulation.fire_brigades.fire_brigade import FireBrigade
from simulation.fire_spread.coef_generator import calculate_beta
from simulation.fire_spread.wind import Wind
from simulation.forest_map import ForestMap
from simulation.forester_patrols.forester_patrol import ForesterPatrol
from simulation.sectors.fire_state import FireState
from simulation.sectors.geographic_direction import GeographicDirection
from simulation.sectors.sector import Sector
import logging

logger = logging.getLogger(__name__)

class Position(NamedTuple):
    latitude: float
    longitude: float

@dataclass
class CalculationContext:
    active_sectors: List
    num_agents: int
    sector_threat: Dict[int, float]
    required_brigades: Dict[int, int]
    agent_locations: Dict[int, Tuple[float, float]]
    sector_locations: Dict[int, Tuple[float, float]]
    agent_to_sector_distances: Dict[Tuple[int, int], float]
    top_sectors: List
    agent_scores: List[Tuple[int, float]]

class OptimizationConfig:
    MIN_DISTANCE_THRESHOLD = 1
    DISTANCE_PENALTY_FACTOR = 2
    MAX_BURN_LEVEL_FOR_EXT = 80.0
    MAX_RANDOM_ATTEMPTS = 8
    MAX_TOTAL_CHILDREN = 30
    AGENT_SECTOR_MULTIPLIER = 2
    TOP_SECTOR_PERCENTAGE = 10
    MAX_COORDINATED_SECTORS = 10
    SUB_TICKS = 50
    SUB_TICK_DELTA = 0.02 # Each sub-tick represents 0.02s of real time (50 * 0.02 = 1s per MCTS step)

class FireSimulationNode(Node):    
    """
        A node representing a specific state in a fire simulation
        within a Monte Carlo Tree Search (MCTS).

        Key aspect is to make sure the sectors and agents state is not 
        shared between nodes, since it could make invalid and false predictions

        Attributes:
            sectors (List[Sector]): List of forest_map sectors for this state in simulation.
            agents (List[Agent]): Firefighting agents.
            time_step (int): Current step in MCTS simulation.
            max_steps (int): Max MCTS simulation steps.
            actions (Optional[List[Tuple[int, int]]]): actions taken by agents in this node
            forest_map (Optional[ForestMap]): Main forest map class. Needed for sector-related calculation.
            wind (Optional[Wind]): Wind class.
            sector_states (FrozenSet): Cached immutable state of all sectors.
            agent_states (Tuple): Cached immutable state of all agents.
            _sector_lookup (Dict): Lookup for sectors by ID.
            _active_sector_ids (FrozenSet): Lookup for sectors with fire.
            reward_strategy (str): Strategy to compute node reward for MCTS.
    """

    def __init__(
        self,
        sectors: List[Sector],
        agents: List[Agent],
        time_step: int,
        max_steps: int = 10,
        action: Optional[List[Tuple[int, int]]] = None,
        forest_map: Optional[ForestMap] = None,
        wind: Optional[Wind] = None,
        sector_states: Optional[FrozenSet[Tuple[int, str, int, int, int]]] = None,
        agent_states: Optional[Tuple[Tuple[str, float, float, Optional[float], Optional[float]], ...]] = None,
        _sector_lookup: Optional[Dict[int, Sector]] = None,
        _active_sector_ids: Optional[FrozenSet[int]] = None,
        reward_strategy: str = ""
    ):
        self.sectors = sectors
        self.reward_strategy = reward_strategy
        self.time_step = time_step
        self.max_steps = max_steps
        self.action = tuple(action) if action else None
        self.map = forest_map
        self.wind = wind or Wind()
        self._children_cache = None
        self.agents = agents
        self._num_fire_brigades = sum(1 for a in agents if isinstance(a, FireBrigade))

        if sector_states is None:
            self.sector_states = frozenset((
                s.sector_id,
                s.fire_state, 
                s.fire_level, 
                s.burn_level, 
                s._number_of_fire_brigades,
                getattr(s, "_last_patrol_step", None),
            ) for s in sectors)
        else:
            self.sector_states = sector_states
                    
        if agent_states is None:
            self.agent_states = tuple((
                a.state, 
                a.location.latitude, 
                a.location.longitude,
                getattr(a.destination, 'latitude', None),
                getattr(a.destination, 'longitude', None)
            ) for a in agents)
        else:
            self.agent_states = agent_states
        
        if _sector_lookup is None:
            self._sector_lookup = {
                s.sector_id: s for s in sectors
            }
        else:
            self._sector_lookup = _sector_lookup
            
        if _active_sector_ids is None:
            self._active_sector_ids = frozenset(s.sector_id for s in sectors if s.fire_level > 0 or s.fire_state == FireState.ACTIVE)
        else:
            self._active_sector_ids = _active_sector_ids

        
    def __hash__(self):
        return hash((self.time_step, self.sector_states, self.agent_states))

    def __eq__(self, other):
        return (isinstance(other, FireSimulationNode) and 
                self.time_step == other.time_step and
                self.sector_states == other.sector_states and
                self.agent_states == other.agent_states)


    def _calculate_all_distances(
        self, 
        agent_locations: Dict, 
        sector_locations: Dict, 
        sector_ids: Set[int], 
        num_agents: int
    ) -> Dict[Tuple[int, int], float]:
        """ 
        Calculate the Euclidean distance between each agent and each sector.
        This is used for generating gready child selection policy. 

        Returns:
            Dictionary: with keys (agent_id, sector_id) and values with the distances agent-sector
        """
        distances = {}
        for agent_id in range(num_agents):
            agent_x, agent_y = agent_locations[agent_id]
            for sector_id in sector_ids:
                sector = sector_locations[sector_id]
                distance = np.hypot(agent_x - sector.latitude, agent_y - sector.longitude)
                distances[(agent_id, sector_id)] = distance
        return distances

    def _calculate_top_k(
        self, 
        num_sectors: int, 
        num_agents: int
    ) -> int:
        """
        Calculates the maximum number of top-K sectors to consider
        in the greedy assignment policy. The scoring logic can be
        influenced by configuration parameters.

        Returns:
            int: Number of top-k sectors
        """
        by_multiplier = num_agents * OptimizationConfig.AGENT_SECTOR_MULTIPLIER
        by_percentage = int(len(self.sectors) * OptimizationConfig.TOP_SECTOR_PERCENTAGE)

        top_k = min(num_sectors, by_multiplier, by_percentage)
        return max(1, top_k)


    def _calculate_agent_scores(
        self, 
        num_agents: int, 
        top_sectors: List,
        sector_threat: Dict[int, float], 
        distances: Dict[Tuple[int, int], float]
    ) -> List[Tuple[int, float]]:
        """
        Scoring for each agent based of sector-thread.
        By scoring i mean: sum(sector_thread/distance_to_sector)

        Also one of approaches to find optimized gready solution. 
        (Use Agents that can response for biggest thread in best time)        

        Returns:
            List[Tulpe] :(agent_id, scoring) sorted desc.
        """
        agent_scores = []

        for agent_id in range(num_agents):
            score = 0.0
            for sector in top_sectors:
                sector_id = sector.sector_id
                score += self._calculate_agent_sector_score(agent_id, sector_id, sector_threat, distances)
            agent_scores.append((agent_id, score))

        agent_scores.sort(key=lambda x: x[1], reverse=True)
        return agent_scores

    def _calculate_agent_sector_score(
        self,
        agent_id: int,
        sector_id: int,
        sector_threat: Dict[int, float],
        distances: Dict[Tuple[int, int], float]
    ) -> float:
        """
        Calculate the score for a given agent and sector based on
        threat and distance with penalty.
        """
        threat = sector_threat[sector_id]
        distance = distances.get((agent_id, sector_id), float('inf'))
        safe_distance = max(OptimizationConfig.MIN_DISTANCE_THRESHOLD, distance)
        return threat / (1 + safe_distance * OptimizationConfig.DISTANCE_PENALTY_FACTOR)

    def _generate_greedy_assignments(self, context: CalculationContext) -> Set:
        """
        Greedy Assignment.

        Assign agents in descending order of their score.
        Each agent is assigned to the sector with the best threat-to-distance ratio.

        Returns:
            Set: Set of child nodes after greedy assignments.
        """
        children = set()
        assigned_sectors = set()
        threat_actions = []
        sector_brigade_counts = collections.defaultdict(int)

        for agent_id, score in context.agent_scores:
            best_assignment = self._find_best_sector_for_agent(
                agent_id, context, assigned_sectors
            )

            if best_assignment:
                sector_id = best_assignment[0]
                required = context.required_brigades.get(sector_id, 0)
                current = sector_brigade_counts[sector_id]
                if current < required:
                    # Map agent_id (new index) back to original index
                    original_agent_id = context._available_agent_mapping[agent_id]
                    threat_actions.append((original_agent_id, sector_id))
                    assigned_sectors.add(sector_id)
                    sector_brigade_counts[sector_id] += 1

        if threat_actions:
            new_state = self._apply_step(threat_actions)
            children.add(new_state)

        return children

    def _find_best_sector_for_agent(
        self,
        agent_id: int,
        context: CalculationContext,
        assigned_sectors: Set[int]
    ) -> Optional[Tuple[int, float]]:
        """
        Find the best sector for the given agent based on the highest score,
        considering only sectors that have not been assigned yet.

        Returns:
            Tuple(sector_id, score) of the best sector, or None if no sector available.
        """
        best_options = []

        for sector_id in context.sector_threat:
            if sector_id in assigned_sectors:
                continue

            score = self._calculate_agent_sector_score(
                agent_id,
                sector_id,
                context.sector_threat,
                context.agent_to_sector_distances
            )
            best_options.append((sector_id, score))

        if not best_options:
            return None

        best_sector = max(best_options, key=lambda x: x[1])
        return best_sector

    def _generate_coordinated_assignments(self, context: CalculationContext) -> Set:
        """
        Coordinated assignment policy.

        Select up to MAX_COORDINATED_SECTORS sectors and assign groups of brigades
        to each. The number of brigades = the maximum needed to extinguish fire.

        This policy tries sending multiple brigades simultaneously to active sectors.
        (Not so effective :( )

        Returns:
            Set: Set of child nodes after applying coordinated assignments.
        """
        children = set()

        if context.num_agents <= 1:
            return children

        max_sectors = min(OptimizationConfig.MAX_COORDINATED_SECTORS, len(context.top_sectors))

        for sector in context.top_sectors[:max_sectors]:
            sector_id = sector.sector_id
            required_brigades = context.required_brigades.get(sector_id, 0)

            if required_brigades == 0:
                continue  

            assignment = self._create_coordinated_assignment(sector_id, required_brigades, context)

            if assignment:
                children.add(self._apply_step(assignment))
        return children

    def _create_coordinated_assignment(self, sector_id: int, required_brigades: int, 
                                 context: CalculationContext) -> List[Tuple[int, int]]:
        """
        Assigns the closest available firefighting brigades to a target sector.

        Returns:
            List[Tuple[int, int]]: A list of (original_agent_id, sector_id) assignments.
        """
        agent_distances = [
            (agent_id, context.agent_to_sector_distances[(agent_id, sector_id)])
            for agent_id in range(context.num_agents)
        ]

        closest_agents = sorted(agent_distances, key=lambda x: x[1])[:min(required_brigades, context.num_agents)]
        # Map back to original agent indices
        mapping = getattr(context, '_available_agent_mapping', list(range(context.num_agents)))
        return [(mapping[agent_id], sector_id) for agent_id, _ in closest_agents]

    def _generate_probabilistic_assignments(self, context: CalculationContext) -> Set:
        """
        Generate a set of unique child nodes by randomly sampling agent-to-sector assignments.
        In current config 80% of all nodes is generated by this assgnment.

        Returns:
            Set[FireSimulationNode]: A set of newly generated child nodes with unique assignments.
        """
        children = set()
        seen_assignments = set()

        max_random = min(
            OptimizationConfig.MAX_RANDOM_ATTEMPTS,
            OptimizationConfig.MAX_TOTAL_CHILDREN - len(children)
        )

        agent_sector_probs = self._calculate_assignment_probabilities(context)

        for i in range(max_random):
            assignment = self._generate_random_assignment(context, agent_sector_probs)

            if assignment and assignment not in seen_assignments:
                seen_assignments.add(assignment)
                child_node = self._apply_step(list(assignment))
                children.add(child_node)
        return children

    def _calculate_assignment_probabilities(self, context: CalculationContext) -> Dict:
        agent_sector_probs: Dict[int, Tuple[List[int], np.ndarray]] = {}
        sector_ids = list(context.sector_threat.keys())

        for agent_id in range(context.num_agents):
            raw_scores = np.array([
                context.sector_threat[sid] / (1 + context.agent_to_sector_distances[(agent_id, sid)])
                for sid in sector_ids
            ])

            total = raw_scores.sum()
            if total > 0:
                probabilities = raw_scores / total
                agent_sector_probs[agent_id] = (sector_ids, probabilities)

        return agent_sector_probs

    def _generate_random_assignment(self, context: CalculationContext, 
                                agent_probs: Dict) -> Optional[Tuple]:
        actions = []
        temp_brigade_counts = collections.defaultdict(int)
        
        # Map back to original agent indices
        mapping = getattr(context, '_available_agent_mapping', list(range(context.num_agents)))
        
        for i in range(context.num_agents):
            if i in agent_probs:
                sector_ids, probs = agent_probs[i]
                chosen = np.random.choice(sector_ids, p=probs)
                
                if temp_brigade_counts[chosen] < context.required_brigades[chosen]:
                    # Use original agent index
                    original_agent_id = mapping[i]
                    actions.append((original_agent_id, chosen))
                    temp_brigade_counts[chosen] += 1
        
        return tuple(sorted(actions)) if actions else None

    def _prepare_calculation_context(self) -> CalculationContext:
        """
            Precomputing
        """
        # Filter active sectors: fire_level > 0 OR fire_state == ACTIVE
        all_active_sectors = [s for s in self.sectors if s.fire_level > 0 or s.fire_state == FireState.ACTIVE]

        active_sectors = [
            s for s in all_active_sectors
            if s.burn_level <= OptimizationConfig.MAX_BURN_LEVEL_FOR_EXT
        ]

        num_agents = self._num_fire_brigades

        sector_threat = {
            s.sector_id: s.fire_level * (1 + s.burn_level)
            for s in active_sectors
        }

        required_brigades = {
            s.sector_id: s.required_fire_brigades() * 2
            for s in active_sectors
        }
        
        # TRAVELLING brigades can be redirected to new targets
        available_agent_indices = []
        for i in range(num_agents):
            agent_state = self.agents[i].state
            if agent_state == AGENT_STATE.AVAILABLE or agent_state == AGENT_STATE.TRAVELLING:
                available_agent_indices.append(i)
        
        num_available = len(available_agent_indices)
        
        if num_available == 0:
            num_agents = 0
            agent_locations = {}
        else:
            agent_locations = {
                new_idx: (self.agents[orig_idx].location.latitude, self.agents[orig_idx].location.longitude)
                for new_idx, orig_idx in enumerate(available_agent_indices)
            }
            num_agents = num_available

        sector_locations = {
            s.sector_id: self.map.get_sector_location(s)
            for s in active_sectors
        }
        
        agent_to_sector_distances = self._calculate_all_distances(
            agent_locations, sector_locations, sector_threat.keys(), num_agents
        )
        
        top_k = self._calculate_top_k(len(active_sectors), num_agents)
        top_sectors = heapq.nlargest(top_k, active_sectors, 
                                    key=lambda s: sector_threat[s.sector_id])
        
        agent_scores = self._calculate_agent_scores(
            num_agents, top_sectors, sector_threat, agent_to_sector_distances
        )
        
        context = CalculationContext(
            active_sectors=active_sectors,
            num_agents=num_agents,
            sector_threat=sector_threat,
            required_brigades=required_brigades,
            agent_locations=agent_locations,
            sector_locations=sector_locations,
            agent_to_sector_distances=agent_to_sector_distances,
            top_sectors=top_sectors,
            agent_scores=agent_scores
        )
        
        context._available_agent_mapping = available_agent_indices if num_agents > 0 else []

        
        return context
    
    def find_children(self):
        """
        Generate all possible child nodes using strategies:
        - Greedy
        - Coordinated
        - Probabilistic

        Returns:
            Set[FireSimulationNode]: A set of unique next possible states (children).
        """
        context = self._prepare_calculation_context()
        
        if context.num_agents == 0:
            # Count how many are executing vs travelling
            executing_count = sum(1 for i in range(self._num_fire_brigades) 
                                 if self.agents[i].state == AGENT_STATE.EXECUTING)
            travelling_count = sum(1 for i in range(self._num_fire_brigades) 
                                 if self.agents[i].state == AGENT_STATE.TRAVELLING)
            available_count = sum(1 for i in range(self._num_fire_brigades) 
                                if self.agents[i].state == AGENT_STATE.AVAILABLE)
            logger.warning(f"MCTS: No available agents - {executing_count} executing (extinguishing), "
                         f"{travelling_count} travelling, {available_count} available")
            self._children_cache = set()
            return self._children_cache
        
        if not context.active_sectors:
            all_active = [s for s in self.sectors if s.fire_level > 0 or s.fire_state == FireState.ACTIVE]
            filtered_out = [s for s in all_active if s.burn_level > OptimizationConfig.MAX_BURN_LEVEL_FOR_EXT]
            logger.warning(f"MCTS: No valid sectors for fire-fighting. "
                         f"Active sectors: {len(all_active)}, "
                         f"Filtered out (burn_level > {OptimizationConfig.MAX_BURN_LEVEL_FOR_EXT}): {len(filtered_out)}")
            self._children_cache = set()
            return self._children_cache
        
        greedy_children = self._generate_greedy_assignments(context)
        coordinated_children = self._generate_coordinated_assignments(context)
        probabilistic_children = self._generate_probabilistic_assignments(context)
        
        children = set()
        children.update(greedy_children)
        children.update(coordinated_children)
        children.update(probabilistic_children)

        total_nodes = len(children)
        greedy_count = len(greedy_children)
        coordinated_count = len(coordinated_children)
        probabilistic_count = len(probabilistic_children)
        
        # print(f"Strategy node counts:")
        # print(f"  Greedy: {greedy_count} nodes ({greedy_count/total_nodes*100:.1f}%)")
        # print(f"  Coordinated: {coordinated_count} nodes ({coordinated_count/total_nodes*100:.1f}%)")
        # print(f"  Probabilistic: {probabilistic_count} nodes ({probabilistic_count/total_nodes*100:.1f}%)")
        # print(f"  Total: {total_nodes} nodes")
        # print()
        
            
        self._children_cache = children
        return children

    def find_random_child(self):
        """
        Randomly generates a single child node by assigning agents to active sectors.
        Optimized for speed - does not generate all children.

        Returns:
            Optional[FireSimulationNode]: A randomly generated child node or None if no active sectors.
        """
        if not self._active_sector_ids:
            return None
        
        # Fast path: context-free random assignment
        active_ids = list(self._active_sector_ids)
        num_available = self._num_fire_brigades # Simplified: try to assign all brigades
        
        if num_available == 0:
            return self._apply_step([])
            
        actions = []
        # Randomly assign each available fire brigade to an active sector
        for i in range(num_available):
            if self.agents[i].state in (AGENT_STATE.AVAILABLE, AGENT_STATE.TRAVELLING):
                target_sector_id = random.choice(active_ids)
                actions.append((i, target_sector_id))
        
        if not actions:
            return self._apply_step([])
            
        return self._apply_step(actions)

    def _apply_step(self, actions: List[Tuple[int, int]]):
        """Apply actions and create new state with optimized object creation.

        The incoming `actions` list contains assignments for fire brigades only
        (indices in range [0, _num_fire_brigades)). Forester patrols receive
        their own deterministic patrol assignments here, based on a simple
        heuristic: patrol sectors that are not burning, prioritising sectors
        that have not been checked for the longest time.
        """
        # Extend actions with heuristic-based patrol assignments.
        patrol_actions: List[Tuple[int, int]] = []
        try:
            patrol_actions = self._generate_patrol_actions()
        except Exception as e:
            logger.error(f"Error generating patrol actions: {e}", exc_info=True)

        if patrol_actions:
            actions = list(actions) + patrol_actions

        sectors_to_modify = set()
        for _, sector_id in actions:
            sectors_to_modify.add(sector_id)
        
        # Optimized: Only clone sectors that will be modified or are adjacent to modified sectors
        # This significantly reduces memory allocation for large sector counts
        sectors_to_clone = set(sectors_to_modify)
        
        # Add adjacent sectors that might be affected by fire spread
        for sector_id in sectors_to_modify:
            sector = self._sector_lookup.get(sector_id)
            if sector and sector.fire_state == FireState.ACTIVE:
                # Add adjacent sectors for potential fire spread
                if self.map:
                    adj_sectors = self.map.get_adjacent_sectors(sector)
                    for adj_sector, _ in adj_sectors:
                        sectors_to_clone.add(adj_sector.sector_id)
        
        new_sectors_map = {}
        new_sectors = []

        # Only clone sectors that need modification
        for s in self.sectors:
            if s.sector_id in sectors_to_clone:
                cloned = s.clone()
                new_sectors_map[s.sector_id] = cloned
                new_sectors.append(cloned)
            else:
                # Reuse existing sector if unchanged
                new_sectors_map[s.sector_id] = s
                new_sectors.append(s)
        
        new_map = self.map.clone()
        new_map.update_sectors(new_sectors)
        
        # Only clone agents that have actions
        agents_with_actions = {a[0] for a in actions}
        new_agents = []
        for i, agent in enumerate(self.agents):
            if i in agents_with_actions:
                new_agent = agent.clone()
                new_agents.append(new_agent)
            else:
                new_agents.append(agent)
        
        for agent_idx, sector_id in actions:
            agent = new_agents[agent_idx]
            dest_sector = new_map.get_sector(sector_id)
            dest_position = new_map.get_sector_location(dest_sector)
            agent.set_state_travelling(dest_position)
        
        # Simulation sub-ticks for agents (movement and extinguishing)
        for _ in range(OptimizationConfig.SUB_TICKS):
            for agent in new_agents:
                if agent.state == AGENT_STATE.TRAVELLING:
                    # Adjust movement delta to sub-ticks
                    if self._update_position(agent, delta=0.005 / OptimizationConfig.SUB_TICKS):
                        agent._location = agent.destination
                    
                        if agent.destination == agent.base_location:
                            agent.set_state_available()
                        else:
                            sec = new_map.find_sector(agent.location)
                            if sec:
                                # Ensure we have a cloned sector for modification
                                if sec.sector_id not in sectors_to_clone:
                                    # This shouldn't happen with our pre-cloning, but for safety:
                                    cloned = sec.clone()
                                    new_sectors_map[sec.sector_id] = cloned
                                    # Replace in new_sectors list too
                                    for i, s in enumerate(new_sectors):
                                        if s.sector_id == sec.sector_id:
                                            new_sectors[i] = cloned
                                            break
                                    sec = cloned
                                    sectors_to_clone.add(sec.sector_id)

                                sec._number_of_fire_brigades += 1
                                agent.set_state_executing()

                if agent.state == AGENT_STATE.EXECUTING:
                    sec = new_map.find_sector(agent.location)
                    if not sec:
                        continue
                        
                    # Ensure we have a cloned sector for modification
                    if sec.sector_id not in sectors_to_clone:
                        cloned = sec.clone()
                        new_sectors_map[sec.sector_id] = cloned
                        for i, s in enumerate(new_sectors):
                            if s.sector_id == sec.sector_id:
                                new_sectors[i] = cloned
                                break
                        sec = cloned
                        sectors_to_clone.add(sec.sector_id)

                    if isinstance(agent, FireBrigade):
                        # Use the new agent-driven extinguishing logic
                        agent.extinguish(OptimizationConfig.SUB_TICK_DELTA, sec)
                    else:
                        # Forester patrols "check" sectors: record patrol time.
                        current_step = self.time_step + 1
                        setattr(sec, "_last_patrol_step", current_step)

                    if hasattr(agent, "is_task_finished") and agent.is_task_finished(sec):
                        agent.set_state_available()

        # Update all sectors to handle fire spread and state changes
        new_active_sector_ids = set()
        for sector in new_sectors:
            # Only update cloned sectors or sectors that might have changed
            if sector.sector_id in sectors_to_clone or sector.fire_state == FireState.ACTIVE:
                sector.update_sector()
            if sector.fire_state == FireState.ACTIVE:
                new_active_sector_ids.add(sector.sector_id)
        
        self._spread_fire(new_sectors, new_map, copy.copy(self.wind), new_active_sector_ids)

        new_sector_states = frozenset((s.sector_id, s.fire_state, s.fire_level, s.burn_level, 
                                      s._number_of_fire_brigades) for s in new_sectors)
                                      
        new_agent_states = tuple((a.state, a.location.latitude, a.location.longitude,
                                getattr(a.destination, 'latitude', None),
                                getattr(a.destination, 'longitude', None)) for a in new_agents)
                                
        new_sector_lookup = {s.sector_id: s for s in new_sectors}
        new_active_sector_ids = frozenset(s.sector_id for s in new_sectors if s.fire_state == FireState.ACTIVE)

        return FireSimulationNode(
            sectors=new_sectors,
            agents=new_agents,
            time_step=self.time_step + 1,
            max_steps=self.max_steps,
            action=actions,
            forest_map=new_map,
            wind=copy.copy(self.wind),
            sector_states=new_sector_states,
            agent_states=new_agent_states,
            _sector_lookup=new_sector_lookup,
            _active_sector_ids=new_active_sector_ids, 
            reward_strategy=self.reward_strategy
        )

    def calculate_reward(self, state):
        print(self.reward_strategy)
        calculator = RewardCalculator(self.reward_strategy)
        return calculator.calculate_reward(state)

    def is_terminal(self):
        """Optimized terminal state check using cached active sectors"""
        return self.time_step >= self.max_steps or not self._active_sector_ids

    def reward(self):
        calculator = RewardCalculator(self.reward_strategy)
        return calculator.calculate_reward(self)

    def _update_position(self, agent: Agent, delta: float = 0.005) -> bool:
        """Update agent position with optimized movement calculation"""
        # delta here is the movement step size
        dest_lat, dest_lon = agent.destination.latitude, agent.destination.longitude
        curr_lat, curr_lon = agent.location.latitude, agent.location.longitude
        
        lat_diff = dest_lat - curr_lat
        lon_diff = dest_lon - curr_lon
        
        agent._location.latitude += min(delta, lat_diff) if lat_diff > 0 else max(-delta, lat_diff)
        agent._location.longitude += min(delta, lon_diff) if lon_diff > 0 else max(-delta, lon_diff)

        return (abs(lat_diff) <= 0.001 and abs(lon_diff) <= 0.001)

    def _spread_fire(self, sectors: List[Sector], forest_map: ForestMap, wind: Wind, active_sector_ids=None):
        """Optimized fire spread simulation using cached data structures"""

        if active_sector_ids is None:
            active_sectors = [s for s in sectors if s.fire_state == FireState.ACTIVE]
        else:
            active_sectors = [s for s in sectors if s.sector_id in active_sector_ids]
        
        sectors_to_activate = []
        sector_lookup = {s.sector_id: s for s in sectors}
        
        adjacency_map = {}
        for sector in active_sectors:
            adjacency_map[sector.sector_id] = forest_map.get_adjacent_sectors(sector)

        for sector in active_sectors:
            for neighbor, direction in adjacency_map[sector.sector_id]:
                if neighbor.fire_state == FireState.INACTIVE:
                    prob = calculate_beta(wind, neighbor.sector_type, direction)
                    if random.random() < prob:
                        sectors_to_activate.append(neighbor)
        
        for sector in sectors_to_activate:
            sector.start_fire()
            
        wind.update_wind()

    def _generate_patrol_actions(self) -> List[Tuple[int, int]]:
        """
        Generate heuristic-based patrol assignments for forester patrols.

        Rules:
        - Patrols ignore burning sectors (fire_state == ACTIVE).
        - Every patrol selects a distinct sector to visit in this step.
        - Priority is given to "older" sectors – those that have not been
          patrolled for the longest time. Sectors never patrolled at all
          are treated as the oldest and will be visited first.
        """
        # Forester patrols are expected to be after fire brigades in self.agents
        patrol_start = self._num_fire_brigades
        if patrol_start >= len(self.agents):
            logger.debug(f"[MCTS] No forester patrols: patrol_start={patrol_start} >= total_agents={len(self.agents)}")
            return []

        patrol_indices = list(range(patrol_start, len(self.agents)))
        if not patrol_indices:
            return []

        # Candidate sectors: all non-burning sectors.
        candidate_sectors = [
            s for s in self.sectors
            if s.fire_state != FireState.ACTIVE
        ]
        if not candidate_sectors:
            return []

        def sector_age(sector: Sector) -> int:
            last_step = getattr(sector, "_last_patrol_step", None)
            if last_step is None:
                # Never patrolled – treat as oldest.
                return self.time_step + 1
            return max(0, self.time_step - last_step)

        # Sort sectors from oldest to newest.
        sorted_sectors = sorted(
            candidate_sectors,
            key=sector_age,
            reverse=True
        )

        actions: List[Tuple[int, int]] = []
        used_sector_ids = set()
        sector_iter = iter(sorted_sectors)

        for patrol_idx in patrol_indices:
            target_sector = None
            while True:
                try:
                    candidate = next(sector_iter)
                except StopIteration:
                    break
                if candidate.sector_id not in used_sector_ids:
                    target_sector = candidate
                    break

            if target_sector is None:
                break

            used_sector_ids.add(target_sector.sector_id)
            actions.append((patrol_idx, target_sector.sector_id))

        return actions

    def simulate_steps_without_action(self, steps: int) -> List[Sector]:
        """Simulate future steps without agent actions - optimized version"""
        active_sectors = {s.sector_id for s in self.sectors if s.fire_state == FireState.ACTIVE}
        
        clones_map = {}
        clones = []
        
        sectors_to_clone = set(active_sectors)
        for s in self.sectors:
            if s.fire_state == FireState.ACTIVE:
                for neighbor, _ in self.map.get_adjacent_sectors(s):
                    sectors_to_clone.add(neighbor.sector_id)
        
        for s in self.sectors:
            if s.sector_id in sectors_to_clone:
                clone = s.clone()
                clones_map[s.sector_id] = clone
                clones.append(clone)
            else:
                clones_map[s.sector_id] = s
                clones.append(s)
        
        fmap = self.map.clone()
        fmap.update_sectors(clones)
        w = copy.copy(self.wind)
        
        active_sector_ids = frozenset(s.sector_id for s in clones if s.fire_state == FireState.ACTIVE)

        for _ in range(steps):
            sectors_to_update = set()
            
            for s_id in active_sector_ids:
                s = clones_map[s_id]
                if s is self._sector_lookup.get(s_id):
                    s = s.clone()
                    clones_map[s_id] = s
                    idx = clones.index(self._sector_lookup[s_id])
                    clones[idx] = s
                s.update_sector()
                
                for neighbor, _ in fmap.get_adjacent_sectors(s):
                    sectors_to_update.add(neighbor.sector_id)
                
            self._spread_fire(clones, fmap, w, active_sector_ids)
            
            active_sector_ids = frozenset(s.sector_id for s in clones if s.fire_state == FireState.ACTIVE)

        return clones

    def simulate_steps_with_action(self, steps: int, actions: List[Tuple[int, int]]) -> Tuple[List[Sector], List[Agent]]:
        active_sectors = {s.sector_id for s in self.sectors if s.fire_state == FireState.ACTIVE}
        
        new_sectors = [s.clone() for s in self.sectors]
        new_sectors_map = {s.sector_id: s for s in new_sectors}

        new_map = self.map.clone()
        new_map.update_sectors(new_sectors)

        new_agents = []
        for i, agent in enumerate(self.agents):
            if any(a[0] == i for a in actions):
                new_agents.append(agent.clone())
            else:
                new_agents.append(agent)
                
        for agent_idx, sector_id in actions:
            agent = new_agents[agent_idx]
            dest_sector = new_map.get_sector(sector_id)
            dest_position = new_map.get_sector_location(dest_sector)
            agent.set_state_travelling(dest_position)

        for _ in range(steps):
            # Sub-ticks for agents
            for _sub in range(OptimizationConfig.SUB_TICKS):
                for agent in new_agents:
                    if agent.state == AGENT_STATE.TRAVELLING:
                        if self._update_position(agent, delta=0.005 / OptimizationConfig.SUB_TICKS):
                            agent._location = agent.destination

                            if agent.destination == agent.base_location:
                                agent.set_state_available()
                            else:
                                sec = new_map.find_sector(agent.location)
                                sec._number_of_fire_brigades += 1
                                agent.set_state_executing()

                    if agent.state == AGENT_STATE.EXECUTING:
                        sec = new_map.find_sector(agent.location)
                        if sec:
                            if sec is not new_sectors_map[sec.sector_id]:
                                sec = sec.clone()
                                new_sectors_map[sec.sector_id] = sec
                                new_map.update_sectors([sec]) 
                            
                            if isinstance(agent, FireBrigade):
                                agent.extinguish(OptimizationConfig.SUB_TICK_DELTA, sec)

                            if agent.is_task_finished(sec):
                                agent.set_state_available()

            new_active_sector_ids = set()
            for sector in new_sectors:
                sector.update_sector()
                if sector.fire_state == FireState.ACTIVE:
                    new_active_sector_ids.add(sector.sector_id)

            self._spread_fire(new_sectors, new_map, copy.copy(self.wind), new_active_sector_ids)

        # print()
        # for a in new_agents:
        #     print(f"Agent {a.fire_brigade_id} state: {a.state.name}")
    
        return new_sectors