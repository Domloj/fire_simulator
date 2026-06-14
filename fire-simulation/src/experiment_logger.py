"""
Experiment Logger for FFSim — Spec section 9.

Per-tick JSONL logging z metrykami eksperymentu:
    tick, burning, burnt, detectionLatency, responseLatency,
    activeAgents, ordersReceived

Aktywowany gdy ``experimentLog`` jest przekazany w /run_simulation.

Użycie:
    logger = ExperimentLogger(path="/tmp/run1.jsonl")
    logger.record_tick(
        tick=engine.tick_count,
        sectors=snapshot.sectors,
        agent_manager=agent_manager,
        orders_this_tick=["EXTINGUISH:14", "PATROL:2"],
        ignition_tick_map=ignition_tick_map,
        first_order_tick_map=first_order_tick_map,
        brigade_dispatch_map=brigade_dispatch_map,
        brigade_arrive_map=brigade_arrive_map,
    )
    logger.close()
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.models.sector import Sector, SectorState
    from src.engine.agent_manager import AgentManager

logger = logging.getLogger(__name__)


class ExperimentLogger:
    """
    Zapisuje metryki symulacji do pliku JSONL (jeden JSON na tick).

    Format per spec section 9:
    {
        "tick": 47,
        "burning": 12,
        "burnt": 5,
        "detectionLatency": 3,
        "responseLatency": 8,
        "activeAgents": 4,
        "ordersReceived": ["EXTINGUISH:14", "PATROL:2"]
    }

    Znaczenia pól:
        tick              — numer bieżącego kroku (od 0).
        burning           — liczba sektorów BURNING.
        burnt             — liczba sektorów ASH lub EXTINGUISHED.
        detectionLatency  — śr. ticki od zapłonu do pierwszego rozkazu
                            dotyczącego danego ogniska; null gdy brak danych.
        responseLatency   — śr. ticki od rozkazu gaszenia do przybycia
                            brygady do sektora; null gdy brak danych.
        activeAgents      — agenci nie będący w AVAILABLE.
        ordersReceived    — lista rozkazów z bieżącego ticku.
    """

    def __init__(self, path: str) -> None:
        """
        Args:
            path: Ścieżka do pliku wyjściowego JSONL.
                  Katalog nadrzędny musi istnieć lub zostanie utworzony.
        """
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = open(self._path, "w", encoding="utf-8", buffering=1)
        logger.info("ExperimentLogger → %s", self._path)

    # ------------------------------------------------------------------
    # Główna metoda — wywołać raz na tick
    # ------------------------------------------------------------------

    def record_tick(
        self,
        tick: int,
        sectors: Dict[int, "Sector"],
        agent_manager: "AgentManager",
        orders_this_tick: Optional[List[str]] = None,
        ignition_tick_map: Optional[Dict[int, int]] = None,
        first_order_tick_map: Optional[Dict[int, int]] = None,
        brigade_dispatch_map: Optional[Dict[int, int]] = None,
        brigade_arrive_map: Optional[Dict[int, int]] = None,
    ) -> None:
        """
        Oblicza metryki i zapisuje jeden rekord JSONL.

        Args:
            tick:               Bieżący numer ticku.
            sectors:            Słownik {sector_id: Sector} aktualnego stanu.
            agent_manager:      Obiekt AgentManager (do statystyk agentów).
            orders_this_tick:   Lista rozkazów otrzymanych w tym ticku,
                                format "AKCJA:sectorId" (np. "EXTINGUISH:14").
            ignition_tick_map:  {sector_id: tick_zapłonu} — aktualizowany
                                przez silnik przy każdym nowym zapłonie.
            first_order_tick_map: {sector_id: tick_rozkazu} — tick, w którym
                                support wydał pierwszy rozkaz dla tego ogniska.
            brigade_dispatch_map: {brigade_id: tick_rozkazu} — tick wysłania
                                rozkazu EXTINGUISH dla brygady.
            brigade_arrive_map:   {brigade_id: tick_przybycia} — tick przybycia
                                brygady do sektora (EXTINGUISHING).
        """
        burning, burnt = self._count_sector_states(sectors)
        detection_latency = self._calc_detection_latency(
            tick, ignition_tick_map or {}, first_order_tick_map or {}
        )
        response_latency = self._calc_response_latency(
            brigade_dispatch_map or {}, brigade_arrive_map or {}
        )
        active_agents = agent_manager.get_active_count()

        record: Dict[str, Any] = {
            "tick": tick,
            "burning": burning,
            "burnt": burnt,
            "detectionLatency": detection_latency,
            "responseLatency": response_latency,
            "activeAgents": active_agents,
            "ordersReceived": orders_this_tick or [],
        }

        self._write(record)

    # ------------------------------------------------------------------
    # Kalkulacja metryk
    # ------------------------------------------------------------------

    @staticmethod
    def _count_sector_states(sectors: Dict[int, "Sector"]) -> tuple[int, int]:
        """Zwraca (burning_count, burnt_count)."""
        # Import lokalny — unikamy kołowego importu na poziomie modułu
        from src.engine.models.sector import SectorState  # type: ignore

        burning = 0
        burnt = 0
        for sector in sectors.values():
            if sector.state == SectorState.BURNING:
                burning += 1
            elif sector.state in (SectorState.ASH, SectorState.EXTINGUISHED):
                burnt += 1
        return burning, burnt

    @staticmethod
    def _calc_detection_latency(
        tick: int,
        ignition_tick_map: Dict[int, int],
        first_order_tick_map: Dict[int, int],
    ) -> Optional[float]:
        """
        Śr. opóźnienie detekcji dla ognisk, dla których wydano rozkaz.

        detectionLatency = avg(first_order_tick - ignition_tick)
        dla wszystkich sector_id w first_order_tick_map.

        Zwraca None gdy brak danych.
        """
        latencies = []
        for sector_id, order_tick in first_order_tick_map.items():
            ign_tick = ignition_tick_map.get(sector_id)
            if ign_tick is not None:
                latencies.append(order_tick - ign_tick)

        if not latencies:
            return None
        return round(sum(latencies) / len(latencies), 2)

    @staticmethod
    def _calc_response_latency(
        brigade_dispatch_map: Dict[int, int],
        brigade_arrive_map: Dict[int, int],
    ) -> Optional[float]:
        """
        Śr. czas odpowiedzi brygad: od rozkazu do przybycia.

        responseLatency = avg(arrive_tick - dispatch_tick)
        dla brygad, które już dotarły.

        Zwraca None gdy brak danych.
        """
        latencies = []
        for brigade_id, arrive_tick in brigade_arrive_map.items():
            dispatch_tick = brigade_dispatch_map.get(brigade_id)
            if dispatch_tick is not None:
                latencies.append(arrive_tick - dispatch_tick)

        if not latencies:
            return None
        return round(sum(latencies) / len(latencies), 2)

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def _write(self, record: Dict[str, Any]) -> None:
        """Zapisuje rekord JSON do pliku (thread-safe, buforowane liniowo)."""
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            try:
                self._file.write(line + "\n")
            except Exception as exc:
                logger.error("ExperimentLogger write failed: %s", exc)

    def close(self) -> None:
        """Zamyka plik logu."""
        with self._lock:
            if not self._file.closed:
                self._file.flush()
                self._file.close()
                logger.info("ExperimentLogger closed: %s", self._path)

    def __del__(self) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"ExperimentLogger(path={self._path}, closed={self._file.closed})"


# ─── Tracker stanu — pomocnicza klasa dla silnika ────────────────────────────

class SimulationMetricsTracker:
    """
    Śledzi dane potrzebne do wyliczenia metryk per tick.

    Silnik (SimulationEngine / EngineHost) tworzy jedną instancję
    i aktualizuje ją po każdej fazie ticku:

        tracker.on_ignition(sector_id, tick)        # faza propagacji
        tracker.on_order_received(sector_id, tick, order_str)  # REST handler
        tracker.on_brigade_dispatched(brigade_id, tick)
        tracker.on_brigade_arrived(brigade_id, tick)

    Następnie przekazuje mappings do ExperimentLogger.record_tick().
    """

    def __init__(self) -> None:
        # sector_id → tick pierwszego zapłonu
        self.ignition_tick_map: Dict[int, int] = {}

        # sector_id → tick pierwszego rozkazu dotyczącego tego ogniska
        self.first_order_tick_map: Dict[int, int] = {}

        # brigade_id → tick wysłania rozkazu EXTINGUISH
        self.brigade_dispatch_map: Dict[int, int] = {}

        # brigade_id → tick przybycia do sektora
        self.brigade_arrive_map: Dict[int, int] = {}

        # Rozkazy z bieżącego ticku (resetowane co tick)
        self._orders_this_tick: List[str] = []

    # ------------------------------------------------------------------
    # Aktualizacje z silnika
    # ------------------------------------------------------------------

    def on_ignition(self, sector_id: int, tick: int) -> None:
        """Wywołać gdy sektor zapłonie po raz pierwszy."""
        if sector_id not in self.ignition_tick_map:
            self.ignition_tick_map[sector_id] = tick

    def on_order_received(
        self, sector_id: int, tick: int, order_str: str
    ) -> None:
        """
        Wywołać gdy support wyda rozkaz dotyczący sektora.

        Args:
            sector_id:  Sektor docelowy rozkazu.
            tick:       Bieżący tick symulacji.
            order_str:  Np. "EXTINGUISH:14" lub "PATROL:2".
        """
        if sector_id not in self.first_order_tick_map:
            self.first_order_tick_map[sector_id] = tick
        self._orders_this_tick.append(order_str)

    def on_brigade_dispatched(self, brigade_id: int, tick: int) -> None:
        """Wywołać gdy brygada dostaje rozkaz EXTINGUISH (przechodzi do TRAVELLING)."""
        if brigade_id not in self.brigade_dispatch_map:
            self.brigade_dispatch_map[brigade_id] = tick

    def on_brigade_arrived(self, brigade_id: int, tick: int) -> None:
        """Wywołać gdy brygada przechodzi do EXTINGUISHING (dotarła do sektora)."""
        if brigade_id not in self.brigade_arrive_map:
            self.brigade_arrive_map[brigade_id] = tick

    # ------------------------------------------------------------------
    # Interfejs dla loggera
    # ------------------------------------------------------------------

    def flush_orders(self) -> List[str]:
        """
        Zwraca rozkazy z bieżącego ticku i resetuje listę.

        Wywołać po ExperimentLogger.record_tick(), przed następnym tickiem.
        """
        orders = self._orders_this_tick
        self._orders_this_tick = []
        return orders

    def snapshot_for_logger(self) -> Dict[str, Any]:
        """
        Zwraca kopię wszystkich mappings do przekazania do record_tick().

        Nie usuwa danych — te są kumulatywne przez całą symulację.
        """
        return {
            "ignition_tick_map": dict(self.ignition_tick_map),
            "first_order_tick_map": dict(self.first_order_tick_map),
            "brigade_dispatch_map": dict(self.brigade_dispatch_map),
            "brigade_arrive_map": dict(self.brigade_arrive_map),
        }