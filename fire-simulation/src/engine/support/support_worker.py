import logging
import threading
import time

logger = logging.getLogger(__name__)

class SupportWorker:
    """Worker for handling decision support logic"""
    def __init__(self, engine):
        self._engine = engine
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        while self._running:
            time.sleep(5)
