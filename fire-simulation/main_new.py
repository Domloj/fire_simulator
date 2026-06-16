"""
Minimal Flask entry point for the spec-compliant SimulationEngine.

Exposes REST endpoints from spec section 5.1 without RabbitMQ/LLM/Backend
dependencies. Suitable for local experimentation and unit-style testing
of the new engine.

Run:  RABBITMQ_HOST=localhost python3 main_new.py
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, request, jsonify

from src.engine.simulation_engine import SimulationEngine
from src.engine.models.sector import Sector, SectorState, SectorType
from src.engine.models.fire_propagation import Wind, FirePropagationConfig
from src.engine.rng_manager import RngManager
from src.engine.agent_manager import AgentManager, Location as AgentLocation
from src.engine.sensors import SensorArray, SensorType, SensorConfig
from src.experiment_logger import ExperimentLogger, SimulationMetricsTracker

logger = logging.getLogger(__name__)
app = Flask(__name__)


class EngineHost:
    """Owns engine lifecycle, background tick loop and concurrency lock."""

    def __init__(self) -> None:
        self.engine: Optional[SimulationEngine] = None
        self.agent_manager: Optional[AgentManager] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.tick_interval: float = 1.0
        self.seed: Optional[int] = None
        self.exp_logger: Optional[ExperimentLogger] = None
        self.metrics_tracker: Optional[SimulationMetricsTracker] = None
        self._support_config: Optional[Dict[str, Any]] = None
        self._support_config_republish: int = 0

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Kolejny start zastępuje poprzednią sesję. Zatrzymujemy ją przed
        # wzięciem locka, bo stop() czeka na wątek pętli, który sam bierze lock.
        if self.is_running():
            self.stop()

        with self._lock:
            self.seed = config.get("seed")
            self.tick_interval = float(
                config.get("tickInterval", config.get("tick_interval", 1.0))
            )

            map_config = config.get("mapConfig", config)
            forest_map = _build_forest_map(map_config)
            self.agent_manager = _build_agent_manager(map_config)

            rng = RngManager(seed=self.seed)
            sensor_array = _build_sensor_array(map_config, rng)
            
            self.engine = SimulationEngine(
                forest_map=forest_map,
                rng=rng,
                fire_config=FirePropagationConfig(),
                simulation_id=str(uuid.uuid4()),
                tick_interval=self.tick_interval,
                agent_manager=self.agent_manager,
            )
            # Assign sensor array for telemetry (spec 5.2.2)
            self.engine.sensor_array = sensor_array

            # Wykrywanie pożaru (Krok 3): domyślnie support widzi sektor dopiero
            # po wykryciu przez sensor/patrol. Można wyłączyć configiem, np. do
            # eksperymentów porównawczych (support znów ma pełną wiedzę).
            self.engine.detection_enabled = bool(
                config.get("detection", map_config.get("detection", True))
            )

            log_path = config.get("experimentLog")
            if log_path:
                self.exp_logger = ExperimentLogger(path=log_path)
                self.metrics_tracker = SimulationMetricsTracker()
                self.engine.metrics_tracker = self.metrics_tracker
            else:
                self.exp_logger = None
                self.metrics_tracker = None

            self.engine.initialize(
                seed=self.seed,
                initial_wind=_parse_wind(map_config.get("wind")),
            )
            ignite_ids = _ignite_initial(self.engine, map_config)
            if self.metrics_tracker:
                for sid in ignite_ids:
                    self.metrics_tracker.on_ignition(int(sid), tick=0)

            # Konfigurację lasu wysyłamy do FFSup (support rozpozna ją po polach
            # location + forestId i ustawi geometrię + bazy agentów). Republikujemy
            # ją przez kilka pierwszych ticków, bo konsument supportu mógł jeszcze
            # nie być gotowy w chwili startu.
            if map_config.get("location") and (
                map_config.get("forestId") is not None or map_config.get("forestName")
            ):
                self._support_config = map_config
                self._support_config_republish = 5
            else:
                self._support_config = None
                self._support_config_republish = 0

            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop, daemon=True, name="SimLoop"
            )
            self._thread.start()
            return {"seed": rng.seed, "simulation_id": self.engine.simulation_id}

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    if self._support_config_republish > 0 and self._support_config:
                        self.engine.rabbitmq_publisher.publish(
                            routing_key="support.data.aggregated",
                            message=self._support_config,
                        )
                        self._support_config_republish -= 1
                    self.engine.step()
                    self._log_current_tick()
            except Exception as exc:
                logger.exception("Simulation tick failed: %s", exc)
                break
            time.sleep(self.tick_interval)

    def _log_current_tick(self) -> None:
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
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
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
        if not self.metrics_tracker:
            return
        order_str = f"{action}:{sector_id or '-'}"
        if sector_id is not None:
            self.metrics_tracker.on_order_received(sector_id, tick, order_str)
        else:
            self.metrics_tracker._orders_this_tick.append(order_str)
        if action == "EXTINGUISH" and brigade_id is not None:
            self.metrics_tracker.on_brigade_dispatched(brigade_id, tick)

    def manual_step(self, ticks: int = 1) -> Dict[str, Any]:
        if self.is_running():
            raise RuntimeError("Cannot manual-step while loop is running")
        with self._lock:
            for _ in range(ticks):
                self.engine.step()
                self._log_current_tick()
            return self.engine.get_snapshot().to_dict()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            if self.engine is None:
                raise RuntimeError("Simulation not initialised")
            return self.engine.get_snapshot().to_dict()


host = EngineHost()


# ─── Config parsing helpers ──────────────────────────────────────────────────

def _sector_type(value: Any) -> SectorType:
    if isinstance(value, SectorType):
        return value
    try:
        return SectorType[str(value).upper()]
    except KeyError:
        return SectorType.UNTRACKED


def _sector_centroid(entry: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Zwraca (lon, lat) sektora: jawne longitude/latitude albo środek z contours."""
    if entry.get("longitude") is not None and entry.get("latitude") is not None:
        return float(entry["longitude"]), float(entry["latitude"])
    contours = entry.get("contours") or []
    if contours:
        lon = sum(p[0] for p in contours) / len(contours)
        lat = sum(p[1] for p in contours) / len(contours)
        return lon, lat
    return None, None


def _build_forest_map(cfg: Dict[str, Any]) -> Dict[int, Sector]:
    """
    Build {sector_id: Sector}. Supports two layouts:
      - flat list of sectors with sectorId/row/column/sectorType
      - explicit rows/columns with auto-generated sectors when omitted
    """
    sectors_cfg: List[Dict[str, Any]] = cfg.get("sectors") or []
    forest: Dict[int, Sector] = {}

    if sectors_cfg:
        for entry in sectors_cfg:
            initial = entry.get("initialState", {}) or {}
            sid = int(entry["sectorId"])
            # config z frontendu trzyma fireLevel w skali 0-100, silnik w 0-1
            raw_fire = float(initial.get("fireLevel", 0.0))
            fire_level = raw_fire / 100.0 if raw_fire > 1.0 else raw_fire
            # config trzyma geometrię jako contours; środek sektora potrzebny
            # by dopasować rozkaz (location) do sektora w agent managerze
            lon, lat = _sector_centroid(entry)
            sector = Sector(
                sector_id=sid,
                row=int(entry["row"]),
                column=int(entry["column"]),
                sector_type=_sector_type(entry.get("sectorType", "MIXED")),
                moisture=float(initial.get("plantLitterMoisture", 0.3)),
                fuel=float(entry.get("fuel", 1.0)),
                fire_level=fire_level,
                temperature=float(initial.get("temperature", 20.0)),
                longitude=lon,
                latitude=lat,
            )
            # sektor z ogniem w configu od razu płonie, inaczej silnik go pominie
            if fire_level > 0.0:
                sector.state = SectorState.BURNING
            forest[sid] = sector
        return forest

    rows = int(cfg.get("rows", 10))
    cols = int(cfg.get("columns", 10))
    for r in range(rows):
        for c in range(cols):
            sid = r * cols + c + 1
            forest[sid] = Sector(
                sector_id=sid,
                row=r,
                column=c,
                sector_type=SectorType.MIXED,
                fuel=1.0,
            )
    return forest


def _build_agent_manager(cfg: Dict[str, Any]) -> AgentManager:
    manager = AgentManager()
    for b in cfg.get("fireBrigades", []) or []:
        loc = b.get("baseLocation", {})
        manager.register_brigade(
            brigade_id=int(b["fireBrigadeId"]),
            base_location=AgentLocation(
                lon=float(loc.get("longitude", 0.0)),
                lat=float(loc.get("latitude", 0.0)),
            ),
        )
    for p in cfg.get("foresterPatrols", []) or []:
        loc = p.get("baseLocation", {})
        manager.register_forester(
            forester_id=int(p["foresterPatrolId"]),
            base_location=AgentLocation(
                lon=float(loc.get("longitude", 0.0)),
                lat=float(loc.get("latitude", 0.0)),
            ),
        )
    return manager


def _build_sensor_array(cfg: Dict[str, Any], rng: RngManager) -> SensorArray:
    """
    Build sensor array from map config (spec 5.2.2).

    Obsługuje dwa formaty pola "sensors":
      - lista obiektów z frontendu/konfiguratora:
        [{"sensorId": 0, "sensorType": "CO2", "location": {...}}, ...]
      - słownik typ -> [sector_id, ...] (format wewnętrzny):
        {"WIND_SPEED": [1, 2], "TEMP_HUMIDITY": [3]}
    """
    sensor_array = SensorArray(rng=rng)
    sensors_config = cfg.get("sensors") or []

    if isinstance(sensors_config, list):
        for entry in sensors_config:
            type_str = entry.get("sensorType")
            try:
                sensor_type = SensorType[type_str]
            except KeyError:
                logger.warning("Unknown sensor type: %s, skipping", type_str)
                continue
            loc = entry.get("location", {}) or {}
            sensor_id = int(entry.get("sensorId", len(sensor_array.sensors)))
            sensor_array.add_sensor(
                sector_id=sensor_id,
                sensor_id=sensor_id,
                sensor_types=[sensor_type],
                location={
                    "lon": float(loc.get("longitude", loc.get("lon", 0.0))),
                    "lat": float(loc.get("latitude", loc.get("lat", 0.0))),
                },
            )
        return sensor_array

    # format słownikowy: typ -> lista sektorów
    sector_sensors: Dict[int, List[SensorType]] = {}
    for sensor_type_str, sector_ids in sensors_config.items():
        try:
            sensor_type = SensorType[sensor_type_str]
        except KeyError:
            logger.warning("Unknown sensor type: %s, skipping", sensor_type_str)
            continue
        for sector_id in (sector_ids or []):
            sector_sensors.setdefault(sector_id, []).append(sensor_type)

    for sector_id, sensor_types in sector_sensors.items():
        sensor_array.add_sensor(
            sector_id=sector_id,
            sensor_id=sector_id * 100,
            sensor_types=sensor_types,
            location={"lon": 0.0, "lat": 0.0},
        )
    return sensor_array


def _parse_wind(wind_cfg: Optional[Dict[str, Any]]) -> Optional[Wind]:
    if not wind_cfg:
        return None
    return Wind(
        speed=float(wind_cfg.get("speed", 0.0)),
        direction_degrees=float(wind_cfg.get("direction_degrees", wind_cfg.get("direction", 0.0))),
    )


def _ignite_initial(engine: SimulationEngine, cfg: Dict[str, Any]) -> List[int]:
    """
    Podpala sektory startowe i zwraca ich listę.

    Gdy config zawiera jawną listę "ignite", używamy jej. W przeciwnym razie
    (np. config z frontendu, gdzie wszystkie sektory mają fireLevel 0) silnik
    sam losuje sektor startowy — zgodnie ze specyfikacją.
    """
    explicit = [int(sid) for sid in (cfg.get("ignite") or [])]
    if explicit:
        for sid in explicit:
            engine.ignite_sector(sid)
        return explicit

    chosen = engine.ignite_random_sector()
    return [chosen] if chosen is not None else []


# ─── REST endpoints (spec section 5.1) ───────────────────────────────────────

@app.route("/run_simulation", methods=["POST"])
def run_simulation():
    data = request.get_json(silent=True) or {}
    try:
        result = host.start(data)
        return jsonify({"status": "ok", **result})
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        logger.exception("run_simulation failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/stop_simulation", methods=["POST"])
def stop_simulation():
    host.stop()
    return jsonify({"status": "ok"})


@app.route("/step", methods=["POST"])
def step():
    data = request.get_json(silent=True) or {}
    ticks = int(data.get("ticks", 1))
    try:
        snap = host.manual_step(ticks)
        return jsonify({"status": "ok", "tick": snap["tick"]})
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409


@app.route("/snapshot", methods=["GET"])
def snapshot():
    try:
        return jsonify({"status": "ok", "snapshot": host.snapshot()})
    except RuntimeError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "running": host.is_running()})


@app.route("/set_speed", methods=["POST"])
def set_speed():
    data = request.get_json(silent=True) or {}
    tick_interval = data.get("tickInterval")
    if tick_interval is None:
        return jsonify({"status": "error", "message": "tickInterval required"}), 400
    try:
        value = float(tick_interval)
        if value <= 0:
            raise ValueError("must be > 0")
    except (TypeError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    host.tick_interval = value
    return jsonify({"status": "ok", "tickInterval": value})


@app.route("/orderFireBrigade", methods=["POST"])
def order_fire_brigade():
    data = request.get_json(silent=True) or {}
    if host.agent_manager is None:
        return jsonify({"status": "error", "message": "Simulation not running"}), 400
    with host._lock:
        result = host.agent_manager.apply_brigade_order(
            data, host.engine.current_snapshot.sectors
        )
        if result.success:
            brigade_id = data.get("fireBrigadeId")
            action = data.get("action", "")
            brigade = host.agent_manager.brigades.get(brigade_id)
            target_sid = brigade.target_sector_id if brigade else None
            host.record_order(action, target_sid, host.engine.tick_count, brigade_id=brigade_id)
    code = 200 if result.success else 400
    return jsonify({
        "status": "ok" if result.success else "error",
        "error_code": result.error_code,
        "message": result.message,
    }), code


@app.route("/orderForestPatrol", methods=["POST"])
def order_forest_patrol():
    data = request.get_json(silent=True) or {}
    if host.agent_manager is None:
        return jsonify({"status": "error", "message": "Simulation not running"}), 400
    with host._lock:
        result = host.agent_manager.apply_forester_order(
            data, host.engine.current_snapshot.sectors
        )
        if result.success:
            action = data.get("action", "")
            forester = host.agent_manager.foresters.get(data.get("foresterPatrolId"))
            target_sid = forester.target_sector_id if forester else None
            host.record_order(action, target_sid, host.engine.tick_count)
    code = 200 if result.success else 400
    return jsonify({
        "status": "ok" if result.success else "error",
        "error_code": result.error_code,
        "message": result.message,
    }), code


@app.route("/assignBrigades", methods=["POST"])
def assign_brigades():
    data = request.get_json(silent=True) or {}
    if host.agent_manager is None:
        return jsonify({"status": "error", "message": "Simulation not running"}), 400
    with host._lock:
        result = host.agent_manager.apply_assign_brigades(
            data, host.engine.current_snapshot.sectors
        )
    code = 200 if result.success else 400
    return jsonify({
        "status": "ok" if result.success else "error",
        "error_code": result.error_code,
        "message": result.message,
    }), code


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    print("FFSim (new engine, spec-compliant) on http://0.0.0.0:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
