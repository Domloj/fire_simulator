import time 
import random
import math
import logging

logger = logging.getLogger(__name__)

def mcts_search(initial_node, time_limit=1.0, return_score=False):
    """
    Monte Carlo Tree Search implementation.
    Uses UCT (Upper Confidence bound applied to Trees) for node selection.
    """
    Q = {}  # Total reward for each node
    N = {}  # Visit count for each node
    children = {}  # Children of each node
    
    def uct(node, parent_n):
        """Upper Confidence Bound for Trees formula"""
        if N.get(node, 0) == 0:
            return float('inf')
        if parent_n == 0:
            parent_n = 1
        exploration_weight = 1.41  # sqrt(2) for UCT1
        exploitation = Q[node] / N[node]
        exploration = exploration_weight * math.sqrt(math.log(parent_n) / N[node])
        return exploitation + exploration
    
    def select(n):
        """Select a path from root to a leaf node using UCT"""
        path = [n]
        current = n
        while current in children and children[current]:
            parent_n = N.get(current, 1)
            current = max(children[current], key=lambda child: uct(child, parent_n))
            path.append(current)
        return path
    
    def expand(node):
        """Expand a node by generating its children"""
        if node in children:
            return children[node]
        children_nodes = node.find_children()
        children[node] = children_nodes
        return children_nodes
    
    def simulate(node):
        """Simulate a random playout from node to terminal state"""
        current = node
        steps = 0
        max_simulation_steps = 100
        
        while not current.is_terminal() and steps < max_simulation_steps:
            child = current.find_random_child()
            if child is None:
                break
            current = child
            steps += 1
        
        return current.reward() if current else 0
    
    def backpropagate(path, reward):
        """Backpropagate reward along the path"""
        for node in reversed(path):
            N[node] = N.get(node, 0) + 1
            Q[node] = Q.get(node, 0) + reward
    
    start = time.time()
    iterations = 0
    
    # Initialize root node
    N[initial_node] = 0
    Q[initial_node] = 0
    
    # First expansion: expand root node
    root_children = expand(initial_node)
    
    if not root_children:
        logger.warning("MCTS: Root node has no children")
        if return_score:
            return [], -float("inf"), None, 0
        else:
            return []
    
    while time.time() - start < time_limit:
        iterations += 1
        
        # Selection: find path from root to leaf
        path = select(initial_node)
        leaf = path[-1]
        
        # Expansion: expand leaf if not terminal
        if not leaf.is_terminal():
            children_nodes = expand(leaf)
            if children_nodes:
                child = random.choice(list(children_nodes))
                path.append(child)
                reward = simulate(child)
            else:
                reward = leaf.reward()
        else:
            reward = leaf.reward()
        
        # Backpropagation: update statistics along path
        backpropagate(path, reward)
    
    # Select best child of root
    if initial_node not in children or not children[initial_node]:
        logger.warning(f"MCTS: No children found after {iterations} iterations")
        if return_score:
            return [], -float("inf"), None, iterations
        else:
            return []
    
    # Choose best child based on average reward (exploitation)
    best_node = max(children[initial_node], key=lambda n: Q.get(n, 0) / (N.get(n) or 1))
    best_score = Q.get(best_node, 0) / (N.get(best_node) or 1)
    
    if return_score:
        action = best_node.action if hasattr(best_node, 'action') else None
        return action, best_score, best_node, iterations
    else:
        action = best_node.action if hasattr(best_node, 'action') else None
        return action
