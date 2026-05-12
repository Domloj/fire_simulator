"""
MCTS worker pool for parallel recommendation generation.

Manages worker threads that process MCTS tasks in parallel with adaptive time limits
and improved scalability.
"""

import logging
import threading
import time
import os
from collections import deque
from typing import Dict, Optional, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, Future

from recomendation.mcts_test import predict
from simulation.forest_map import ForestMap
from simulation.sectors.fire_state import FireState

logger = logging.getLogger(__name__)

DEFAULT_NUM_WORKERS = max(4, min(os.cpu_count() or 4, 8))

class MCTSWorkerPool:
    """Pool of worker threads for MCTS computation with adaptive time limits"""
    
    def __init__(self, num_workers: int = None):
        """
        Initialize MCTS worker pool.
        
        Args:
            num_workers: Number of worker threads. If None, uses adaptive default.
        """
        self._num_workers = num_workers or DEFAULT_NUM_WORKERS
        self._worker_threads: List[threading.Thread] = []
        self._task_queue = deque()
        self._task_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._active_tasks = 0
        self._active_tasks_lock = threading.Lock()
    
    def start(self):
        """Start worker threads"""
        for i in range(self._num_workers):
            thread = threading.Thread(target=self._worker_loop, args=(i,), daemon=False, name=f"MCTSWorker-{i}")
            thread.start()
            self._worker_threads.append(thread)
        logger.info(f"Started {self._num_workers} MCTS worker threads")
    
    def stop(self):
        """Stop worker threads and clear task queue"""
        logger.info("Stopping MCTS worker pool...")
        self._stop_event.set()
        
        # Clear all pending tasks from queue
        with self._task_lock:
            pending_count = len(self._task_queue)
            if pending_count > 0:
                logger.info(f"Clearing {pending_count} pending MCTS tasks from queue")
                # Mark all pending tasks as completed/error
                for task in self._task_queue:
                    if not task.get('completed'):
                        task['completed'] = True
                        task['error'] = 'Worker pool stopped'
                        task['result'] = None
                self._task_queue.clear()
        
        for thread in self._worker_threads:
            if thread and thread.is_alive():
                try:
                    logger.debug(f"Waiting for worker thread {thread.name} to stop...")
                    thread.join(timeout=5.0)
                    if thread.is_alive():
                        logger.warning(f"Worker thread {thread.name} did not stop within timeout")
                    else:
                        logger.debug(f"Worker thread {thread.name} stopped")
                except Exception as e:
                    logger.error(f"Error waiting for worker thread {thread.name}: {e}", exc_info=True)
        
        self._worker_threads.clear()
        
        # Reset active tasks counter
        with self._task_lock:
            self._active_tasks = 0
        
        logger.info("MCTS worker pool stopped and cleaned up")
    
    def _calculate_adaptive_timeout(self, forest_map: ForestMap) -> float:
        """
        Calculate adaptive timeout based on problem complexity.
        
        Args:
            forest_map: ForestMap to analyze
            
        Returns:
            Adaptive timeout in seconds
        """

        sectors = [s for row in forest_map.sectors for s in row]
        active_fires = sum(1 for s in sectors if s.fire_state == FireState.ACTIVE)
        total_sectors = len(sectors)
        num_agents = len(forest_map.fireBrigades) + len(getattr(forest_map, "foresterPatrols", []))
        base_timeout = 4.0  # Increased from 2.0 for longer learning
        fire_factor = 1.0 + (active_fires * 0.3)
        sector_factor = 1.0 + min(total_sectors / 20.0, 1.0)
        agent_factor = 1.0 + (num_agents * 0.1)
        timeout = min(base_timeout * fire_factor * sector_factor * agent_factor, 12.0)  # Increased max from 8.0 to 12.0
        
        return max(timeout, 3.0)  # Increased min from 1.5 to 3.0 for better quality
    
    def submit_task(self, forest_map: ForestMap, timeout: float = None) -> Optional[Dict[str, Any]]:
        """
        Submit MCTS task and wait for result with adaptive timeout.
        
        Args:
            forest_map: ForestMap to analyze
            timeout: Maximum time to wait for result (seconds). If None, uses adaptive calculation.
        
        Returns:
            Dict with 'actions' and 'reasoning', or None if timeout/error
        """
        if timeout is None:
            timeout = self._calculate_adaptive_timeout(forest_map)
        
        task = {
            'forest_map': forest_map,
            'result': None,
            'completed': False,
            'error': None,
            'timeout': timeout
        }
        
        with self._task_lock:
            self._task_queue.append(task)
        
        logger.debug(f"MCTS task submitted to queue (adaptive timeout: {timeout:.2f}s)")
        start_time = time.time()
        poll_interval = 0.05  # Faster polling for responsiveness
        
        while not task['completed'] and (time.time() - start_time) < timeout:
            time.sleep(poll_interval)
        
        if not task['completed']:
            logger.warning(f"MCTS task timed out after {timeout:.2f}s")
            return None
        
        if task.get('error'):
            logger.error(f"MCTS task failed: {task['error']}")
            return None
        
        return task.get('result')
    
    def _worker_loop(self, worker_id: int):
        """Worker thread loop with improved error handling"""
        logger.info(f"MCTS worker {worker_id} started")
        
        while not self._stop_event.is_set():
            try:
                task = None
                with self._task_lock:
                    if self._task_queue:
                        task = self._task_queue.popleft()
                        self._active_tasks += 1
                
                if task:
                    try:
                        logger.debug(f"Worker {worker_id} processing MCTS task (timeout: {task.get('timeout', 'default')}s)")
                        start_time = time.time()
                        
                        result = predict(task['forest_map'])
                        
                        elapsed = time.time() - start_time
                        task['result'] = result
                        task['completed'] = True
                        
                        num_recs = len(result.get('actions', []))
                        logger.info(f"Worker {worker_id} completed task: {num_recs} recommendations in {elapsed:.2f}s")
                    except Exception as e:
                        logger.error(f"Worker {worker_id} error processing task: {e}", exc_info=True)
                        task['error'] = str(e)
                        task['completed'] = True
                    finally:
                        with self._task_lock:
                            self._active_tasks = max(0, self._active_tasks - 1)
                else:
                    time.sleep(0.1)  # Reduced sleep for better responsiveness
                    
            except Exception as e:
                logger.error(f"Worker {worker_id} unexpected error: {e}", exc_info=True)
                time.sleep(0.5)
        
        logger.info(f"MCTS worker {worker_id} stopped")
