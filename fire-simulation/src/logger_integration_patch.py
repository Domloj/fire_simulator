"""
Patch integracyjny — Krok 5: Logowanie eksperymentów.

Pokazuje MINIMALNE zmiany wymagane w main_new.py i simulation_engine.py,
żeby podłączyć ExperimentLogger i SimulationMetricsTracker bez przepisywania
istniejącego kodu.

────────────────────────────────────────────────────────────────────────────
CZĘŚĆ A — zmiany w main_new.py (EngineHost)
────────────────────────────────────────────────────────────────────────────

1. Import na górze pliku:

    from experiment_logger import ExperimentLogger, SimulationMetricsTracker

2. W EngineHost.__init__() dodaj pola:

    self.exp_logger: Optional[ExperimentLogger] = None
    self.metrics_tracker: Optional[SimulationMetricsTracker] = None

3. W EngineHost.start() — po zbudowaniu engine, przed pętlą:

    log_path = config.get("experimentLog")
    if log_path:
        self.exp_logger = ExperimentLogger(path=log_path)
        self.metrics_tracker = SimulationMetricsTracker()
        # Przekaż tracker do engine żeby mógł rejestrować zapłony / przybycia
        self.engine.metrics_tracker = self.metrics_tracker
    else:
        self.exp_logger = None
        self.metrics_tracker = None

4. W EngineHost._run_loop() — po engine.step():

    if self.exp_logger and self.metrics_tracker:
        snap = self.engine.current_snapshot
        self.exp_logger.record_tick(
            tick=snap.tick,
            sectors=snap.sectors,
            agent_manager=self.agent_manager,
            orders_this_tick=self.metrics_tracker.flush_orders(),
            **self.metrics_tracker.snapshot_for_logger(),
        )

5. W EngineHost.stop() — przed thread.join():

    if self.exp_logger:
        self.exp_logger.close()
        self.exp_logger = None

6. W REST handlerach orderFireBrigade / orderForestPatrol — po udanej walidacji:

    # Przykład dla orderFireBrigade:
    if result.success and host.metrics_tracker:
        sector_id = data.get("location")  # lub target_sector_id z result
        tick = host.engine.tick_count
        # "EXTINGUISH:14"  lub "GO_TO_BASE:-"
        action = data.get("action", "?")
        target_sid = result.target_sector_id   # dodaj to pole do OrderResult
        order_str = f"{action}:{target_sid or '-'}"
        host.metrics_tracker.on_order_received(target_sid, tick, order_str)

────────────────────────────────────────────────────────────────────────────
CZĘŚĆ B — zmiany w simulation_engine.py (SimulationEngine)
────────────────────────────────────────────────────────────────────────────

1. Dodaj opcjonalne pole w __init__:

    self.metrics_tracker = None   # ustawiany z zewnątrz przez EngineHost

2. W _phase_fire_propagation(), przy zapłonie sektora — po linii:
       neighbor_next.state = SectorState.BURNING

   Dodaj:
       if self.metrics_tracker:
           self.metrics_tracker.on_ignition(
               sector_id=neighbor_id,
               tick=self.tick_count + 1,
           )

3. W agent_manager.py — w _tick_travel(), gdy brygada przechodzi do EXTINGUISHING:

   Dodaj hook przez AgentEvent — silnik już zwraca listę AgentEvent z process_tick().
   Po wywołaniu process_tick() w engine.step(), przeskanuj eventy:

       for event in self.last_events:
           if (self.metrics_tracker and
                   event.event_type == AgentEventType.BRIGADE_ARRIVED):
               self.metrics_tracker.on_brigade_arrived(
                   event.agent_id, self.tick_count + 1
               )

   Przy rozkazie EXTINGUISH (w orderFireBrigade REST handler):
       if result.success and host.metrics_tracker:
           host.metrics_tracker.on_brigade_dispatched(brigade_id, tick)

────────────────────────────────────────────────────────────────────────────
CZĘŚĆ C — format wyjściowy JSONL (spec section 9)
────────────────────────────────────────────────────────────────────────────

Każda linia pliku jest samodzielnym obiektem JSON:

    {"tick": 0, "burning": 1, "burnt": 0, "detectionLatency": null, "responseLatency": null, "activeAgents": 0, "ordersReceived": []}
    {"tick": 1, "burning": 3, "burnt": 0, "detectionLatency": null, "responseLatency": null, "activeAgents": 0, "ordersReceived": []}
    {"tick": 5, "burning": 5, "burnt": 0, "detectionLatency": 3, "responseLatency": null, "activeAgents": 2, "ordersReceived": ["EXTINGUISH:2"]}
    {"tick": 10, "burning": 3, "burnt": 2, "detectionLatency": 3.0, "responseLatency": 5.0, "activeAgents": 2, "ordersReceived": []}

────────────────────────────────────────────────────────────────────────────
CZĘŚĆ D — wywołanie /run_simulation z logowaniem
────────────────────────────────────────────────────────────────────────────

    POST /run_simulation
    {
        "seed": 42,
        "experimentLog": "/tmp/experiment_run1.jsonl",
        "mapConfig": {
            "rows": 10,
            "columns": 10,
            "wind": { "speed": 15.0, "direction_degrees": 90 },
            "ignite": [55]
        }
    }

Pole "experimentLog" jest opcjonalne — pominięcie go wyłącza logowanie.
"""

# Ten plik jest dokumentacją/patchem integracyjnym.
# Nie wymaga uruchomienia — jest instrukcją dla dewelopera.

# Poniżej — skrócona, działająca wersja EngineHost z logowaniem wbudowanym,
# do użycia jako wzorzec albo bezpośredniego podmiany klasy w main_new.py.

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EngineHostWithLogging:
    """
    Rozszerzona wersja EngineHost z obsługą ExperimentLogger.

    Można podmienić bezpośrednio klasę EngineHost w main_new.py lub
    użyć jako wzorca do wprowadzenia zmian.
    """

    def __init__(self) -> None:
        # Oryginalne pola z EngineHost
        from src.engine.simulation_engine import SimulationEngine
        from src.engine.agent_manager import AgentManager

        self.engine: Optional[SimulationEngine] = None
        self.agent_manager: Optional[AgentManager] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.tick_interval: float = 1.0
        self.seed: Optional[int] = None

        # Nowe pola — logowanie
        try:
            from experiment_logger import ExperimentLogger, SimulationMetricsTracker
            self._logger_cls = ExperimentLogger
            self._tracker_cls = SimulationMetricsTracker
        except ImportError:
            self._logger_cls = None
            self._tracker_cls = None

        self.exp_logger: Optional[Any] = None
        self.metrics_tracker: Optional[Any] = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Uruchomienie symulacji — rozszerzone o inicjalizację loggera."""
        # (Oryginalna logika start() z main_new.py — skrócona do demonstracji)
        with self._lock:
            if self.is_running():
                raise RuntimeError("Simulation already running")

            # … (budowanie engine jak w oryginale) …

            # ── Inicjalizacja loggera eksperymentu ──────────────────────
            log_path = config.get("experimentLog")
            if log_path and self._logger_cls:
                self.exp_logger = self._logger_cls(path=log_path)
                self.metrics_tracker = self._tracker_cls()
                if self.engine:
                    self.engine.metrics_tracker = self.metrics_tracker
                logger.info("Experiment logging → %s", log_path)

            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True, name="SimLoop"
            )
            self._thread.start()

            rng_seed = self.engine.rng.seed if self.engine else None
            sim_id = self.engine.simulation_id if self.engine else str(uuid.uuid4())
            return {"seed": rng_seed, "simulation_id": sim_id}

    def _run_loop(self) -> None:
        """Pętla tików z wywołaniem loggera po każdym ticku."""
        while not self._stop.is_set():
            try:
                with self._lock:
                    self.engine.step()
                    self._log_current_tick()
            except Exception as exc:
                logger.exception("Simulation tick failed: %s", exc)
                break
            time.sleep(self.tick_interval)

    def _log_current_tick(self) -> None:
        """Zapisuje metryki bieżącego ticku (tylko gdy logger aktywny)."""
        if not self.exp_logger or not self.metrics_tracker or not self.engine:
            return

        snap = self.engine.current_snapshot
        self.exp_logger.record_tick(
            tick=snap.tick,
            sectors=snap.sectors,
            agent_manager=self.agent_manager,
            orders_this_tick=self.metrics_tracker.flush_orders(),
            **self.metrics_tracker.snapshot_for_logger(),
        )

    def stop(self) -> None:
        """Zatrzymuje symulację i zamyka logger."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

        # Zamknij logger po zakończeniu pętli
        if self.exp_logger:
            self.exp_logger.close()
            self.exp_logger = None

    def record_order(
        self,
        action: str,
        sector_id: Optional[int],
        tick: int,
        brigade_id: Optional[int] = None,
    ) -> None:
        """
        Pomocnicza metoda — wywołać z REST handlerów po udanym rozkazie.

        Args:
            action:     "EXTINGUISH", "PATROL", "GO_TO_BASE"
            sector_id:  Sektor docelowy (None dla GO_TO_BASE do bazy)
            tick:       Bieżący tick symulacji
            brigade_id: ID brygady (tylko dla EXTINGUISH)
        """
        if not self.metrics_tracker:
            return

        order_str = f"{action}:{sector_id or '-'}"

        if sector_id is not None:
            self.metrics_tracker.on_order_received(sector_id, tick, order_str)
        else:
            # GO_TO_BASE bez sektora — dodaj do listy rozkazów bez latency tracking
            self.metrics_tracker._orders_this_tick.append(order_str)

        if action == "EXTINGUISH" and brigade_id is not None:
            self.metrics_tracker.on_brigade_dispatched(brigade_id, tick)