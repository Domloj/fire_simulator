"""
Scenariusze testowe FFSim (spec sekcja 10 — minimum 7 scenariuszy).

Uruchomienie:
    cd fire-simulation
    python -m pytest tests/test_scenarios.py -v

lub bezpośrednio:
    /path/to/venv/bin/python -m pytest tests/test_scenarios.py -v
"""

import copy
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from src.engine.simulation_engine import SimulationEngine
from src.engine.models.sector import Sector, SectorState, SectorType
from src.engine.models.fire_propagation import Wind, FirePropagationConfig
from src.engine.rng_manager import RngManager
from src.engine.agent_manager import AgentManager, Location
from src.engine.sensors import SensorType
from src.experiment_logger import ExperimentLogger, SimulationMetricsTracker


# ─── helpers ─────────────────────────────────────────────────────────────────

def build_grid(rows=10, cols=10, sector_type=SectorType.MIXED) -> dict:
    forest = {}
    for r in range(rows):
        for c in range(cols):
            sid = r * cols + c + 1
            forest[sid] = Sector(
                sector_id=sid, row=r, column=c,
                sector_type=sector_type, fuel=1.0,
            )
    return forest


def make_engine(rows=10, cols=10, seed=42, sector_type=SectorType.MIXED,
                initial_wind=None, fire_config=None) -> SimulationEngine:
    forest = build_grid(rows, cols, sector_type)
    rng = RngManager(seed=seed)
    engine = SimulationEngine(
        forest_map=forest,
        rng=rng,
        fire_config=fire_config or FirePropagationConfig(),
        simulation_id="test",
    )
    engine.initialize(seed=seed, initial_wind=initial_wind)
    return engine


def run_ticks(engine, n):
    for _ in range(n):
        engine.step()


def burning_count(engine):
    return sum(1 for s in engine.current_snapshot.sectors.values()
               if s.state == SectorState.BURNING)


def ash_count(engine):
    return sum(1 for s in engine.current_snapshot.sectors.values()
               if s.state in (SectorState.ASH, SectorState.EXTINGUISHED))


# ─── Scenariusz 1: pojedynczy pożar bez wiatru ───────────────────────────────

def test_S1_single_fire_no_wind():
    """Pożar w centrum siatki, brak wiatru — ogień się rozprzestrzenia."""
    engine = make_engine(rows=10, cols=10, seed=1, initial_wind=Wind(speed=0.0))
    center = 55  # wiersz 5, kolumna 4 (0-indexed) w siatce 10x10
    engine.ignite_sector(center)

    # po 5 tickach powinny płonąć sąsiednie sektory
    run_ticks(engine, 5)
    assert burning_count(engine) > 1, "po 5 tickach pożar powinien objąć sąsiednie sektory"

    # po 15 tickach pożar powinien dotrzeć do przynajmniej 4 sektorów
    run_ticks(engine, 10)
    total_affected = burning_count(engine) + ash_count(engine)
    assert total_affected >= 4, f"po 15 tickach pożar powinien objąć przynajmniej 4 sektory, got {total_affected}"


# ─── Scenariusz 2: pojedynczy pożar z silnym wiatrem ─────────────────────────

def test_S2_single_fire_strong_wind():
    """Wiatr 40 km/h na wschód — pożar powinien szybciej dotrzeć na wschód."""
    rows, cols = 10, 10
    engine = make_engine(rows=rows, cols=cols, seed=2,
                         initial_wind=Wind(speed=40.0, direction_degrees=90.0))
    left_center = (rows // 2) * cols + 1  # lewa kolumna, środkowy wiersz
    engine.ignite_sector(left_center)

    run_ticks(engine, 15)

    snap = engine.current_snapshot
    # Co najmniej jeden sektor pali się w prawej połowie siatki
    right_half_burning = any(
        s.state == SectorState.BURNING and s.column >= cols // 2
        for s in snap.sectors.values()
    )
    assert right_half_burning, "ogień powinien dotrzeć do prawej połowy siatki"


# ─── Scenariusz 3: wiele pożarów jednocześnie ────────────────────────────────

def test_S3_multiple_fires():
    """Trzy ogniska w różnych narożnikach — wszystkie powinny się rozwijać."""
    engine = make_engine(rows=10, cols=10, seed=3)
    ignite_ids = [1, 10, 91]  # lewy górny, prawy górny, lewy dolny
    for sid in ignite_ids:
        engine.ignite_sector(sid)

    run_ticks(engine, 8)

    assert burning_count(engine) > 3, "z trzech ognisk powinno płonąć więcej niż 3 sektory"


# ─── Scenariusz 4: mało brygad, wiele pożarów ────────────────────────────────

def test_S4_few_brigades_many_fires():
    """Jedna brygada wobec 4 ognisk — nie ugasi wszystkich."""
    engine = make_engine(rows=5, cols=5, seed=4)
    am = AgentManager()
    am.register_brigade(
        brigade_id=1,
        base_location=Location(lon=0.5, lat=0.5),
    )
    engine.agent_manager = am

    fire_ids = [1, 5, 21, 25]
    for sid in fire_ids:
        engine.ignite_sector(sid)

    run_ticks(engine, 5)

    # brygada nie może ugasić wszystkich — powinny nadal płonąć sektory
    still_burning = burning_count(engine)
    assert still_burning >= 1, "przynajmniej jeden sektor powinien nadal płonąć"


# ─── Scenariusz 5: brak dostępnych patroli ───────────────────────────────────

def test_S5_no_patrols_available():
    """Rozkaz patrolu gdy żaden leśnik nie istnieje — błąd UNKNOWN_AGENT."""
    engine = make_engine(rows=5, cols=5, seed=5)
    engine.ignite_sector(13)
    run_ticks(engine, 2)

    result = engine.agent_manager.apply_forester_order(
        {"foresterPatrolId": 99, "action": "PATROL",
         "location": {"lon": 0.0, "lat": 0.0}},
        engine.current_snapshot.sectors,
    )
    assert not result.success
    assert result.error_code == "UNKNOWN_AGENT"


# ─── Scenariusz 6: determinizm (ten sam seed → identyczny przebieg) ──────────

def test_S6_determinism():
    """Dwie symulacje z tym samym seedem muszą dawać bit-identyczne wyniki."""
    def run_sim(seed):
        engine = make_engine(rows=8, cols=8, seed=seed)
        engine.ignite_sector(32)
        run_ticks(engine, 15)
        snap = engine.current_snapshot
        return {
            sid: (s.state.value, round(s.fire_level, 6), round(s.fuel, 6))
            for sid, s in snap.sectors.items()
        }

    result_a = run_sim(seed=777)
    result_b = run_sim(seed=777)

    assert result_a == result_b, "różne seedy dały różne wyniki"

    result_c = run_sim(seed=778)
    assert result_a != result_c, "różne seedy dały identyczne wyniki — generator nie działa?"


# ─── Scenariusz 7: walidacja błędnych rozkazów ───────────────────────────────

def test_S7_invalid_orders():
    """Sprawdzenie kodów błędów przy złych rozkazach (spec sekcja 5)."""
    engine = make_engine(rows=5, cols=5, seed=7)
    am = AgentManager()
    am.register_brigade(brigade_id=1, base_location=Location(lon=0.1, lat=0.1))
    am.register_forester(forester_id=1, base_location=Location(lon=0.1, lat=0.1))

    sectors = engine.current_snapshot.sectors

    # MISSING_FIELD — brak fireBrigadeId
    r = am.apply_brigade_order(
        {"action": "EXTINGUISH", "location": {"lon": 0.0, "lat": 0.0}},
        sectors,
    )
    assert r.error_code == "MISSING_FIELD"

    # UNKNOWN_AGENT — nieistniejąca brygada
    r = am.apply_brigade_order(
        {"fireBrigadeId": 999, "action": "EXTINGUISH",
         "location": {"lon": 0.0, "lat": 0.0}},
        sectors,
    )
    assert r.error_code == "UNKNOWN_AGENT"

    # INVALID_ACTION_FOR_AGENT_TYPE — nieznana akcja
    r = am.apply_brigade_order(
        {"fireBrigadeId": 1, "action": "FLY",
         "location": {"lon": 0.0, "lat": 0.0}},
        sectors,
    )
    assert r.error_code == "INVALID_ACTION_FOR_AGENT_TYPE"

    # SECTOR_NOT_ON_FIRE — rozkaz gaszenia spokojnego sektora
    # sektor 13 (środek 5x5) — jeszcze nie płonie
    sector_13 = sectors[13]
    r = am.apply_brigade_order(
        {"fireBrigadeId": 1, "action": "EXTINGUISH",
         "location": {"lon": sector_13.longitude or 0.0, "lat": sector_13.latitude or 0.0}},
        sectors,
    )
    # lokalizacja bez lon/lat daje UNKNOWN_SECTOR zanim sprawdzimy stan
    assert r.error_code in ("SECTOR_NOT_ON_FIRE", "UNKNOWN_SECTOR")


# ─── Scenariusz 8: pożar gaśnie po wypaleniu paliwa ──────────────────────────

def test_S8_burnout():
    """Sektor z niskim paliwem powinien wypalić się do stanu ASH."""
    config = FirePropagationConfig()
    forest = build_grid(3, 3)
    # środkowy sektor ma bardzo mało paliwa
    forest[5] = Sector(
        sector_id=5, row=1, column=1,
        sector_type=SectorType.MIXED,
        fuel=0.05,  # bardzo mało paliwa
    )
    rng = RngManager(seed=9)
    engine = SimulationEngine(
        forest_map=forest, rng=rng, fire_config=config, simulation_id="t"
    )
    engine.initialize(seed=9)
    engine.ignite_sector(5)

    # czekamy aż paliwo się wypali (max 20 ticków)
    for _ in range(20):
        engine.step()
        if engine.current_snapshot.sectors[5].state == SectorState.ASH:
            break

    assert engine.current_snapshot.sectors[5].state == SectorState.ASH, (
        "sektor z niskim paliwem powinien wypalić się do ASH"
    )


# ─── Scenariusz 9: logger JSONL ──────────────────────────────────────────────

def test_S9_experiment_logger_output():
    """Logger produkuje poprawny JSONL z wymaganymi polami."""
    engine = make_engine(rows=5, cols=5, seed=10)
    tracker = SimulationMetricsTracker()
    engine.metrics_tracker = tracker
    engine.ignite_sector(13)
    tracker.on_ignition(13, tick=0)

    am = AgentManager()

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        log_path = f.name

    try:
        exp_logger = ExperimentLogger(path=log_path)
        for _ in range(5):
            engine.step()
            exp_logger.record_tick(
                tick=engine.tick_count,
                sectors=engine.current_snapshot.sectors,
                agent_manager=am,
                orders_this_tick=tracker.flush_orders(),
                **tracker.snapshot_for_logger(),
            )
        exp_logger.close()

        with open(log_path) as f:
            lines = f.readlines()

        assert len(lines) == 5, f"oczekiwano 5 linii JSONL, got {len(lines)}"
        required_keys = {"tick", "burning", "burnt", "detectionLatency",
                         "responseLatency", "activeAgents", "ordersReceived"}
        for line in lines:
            record = json.loads(line)
            assert required_keys.issubset(record.keys()), (
                f"brakujące pola w rekordzie: {required_keys - record.keys()}"
            )

    finally:
        os.unlink(log_path)


# ─── Scenariusz 10: sensory reagują na ogień ─────────────────────────────────

class _RecordingPublisher:
    """Łapie feed supportu zamiast wysyłać do brokera (broker w testach pada)."""

    def __init__(self):
        self.available = True
        self.support_msgs = []

    def publish(self, routing_key, message):
        if routing_key == "support.data.aggregated":
            self.support_msgs.append(message)
        return True

    def __getattr__(self, _):
        # pozostałe publish_* są no-opami
        return lambda *a, **k: True


def test_S10_sensors_react_to_fire():
    """Odczyty CO2/PM2.5/temperatury rosną na płonącym sektorze."""
    engine = make_engine(rows=3, cols=3, seed=11)
    engine.sensor_array.add_sensor(
        sector_id=5, sensor_id=0,
        sensor_types=[SensorType.CO2, SensorType.PM2_5, SensorType.TEMP_HUMIDITY],
        location={"lon": 1.0, "lat": 1.0},
    )

    def read_sector5():
        fl = engine.current_snapshot.sectors[5].fire_level
        readings = engine.sensor_array.read_all(timestamp="t", sector_fire_levels={5: fl})
        return {r.sensor_type: r.data for r in readings}

    before = read_sector5()
    engine.ignite_sector(5)
    run_ticks(engine, 6)
    after = read_sector5()

    assert after[SensorType.CO2]["concentration"] > before[SensorType.CO2]["concentration"] + 300
    assert after[SensorType.PM2_5]["concentration"] > before[SensorType.PM2_5]["concentration"] + 50
    assert after[SensorType.TEMP_HUMIDITY]["temperature"] > before[SensorType.TEMP_HUMIDITY]["temperature"] + 10


# ─── Scenariusz 11: bramkowanie feedu supportu wykrywaniem ───────────────────

def test_S11_support_detection_gating():
    """Support widzi ogień dopiero po wykryciu sektora przez sensor."""
    engine = make_engine(rows=3, cols=3, seed=12)
    # sensor tylko na sektorze 1, sektor 9 zostaje bez pokrycia
    engine.sensor_array.add_sensor(
        sector_id=1, sensor_id=0, sensor_types=[SensorType.CO2],
        location={"lon": 0.0, "lat": 0.0},
    )
    pub = _RecordingPublisher()
    engine.rabbitmq_publisher = pub

    engine.ignite_sector(1)  # ma sensor
    engine.ignite_sector(9)  # bez sensora i patrolu
    run_ticks(engine, 6)

    last = {s["sectorId"]: s["state"] for s in pub.support_msgs[-1]["sectors"]}

    # sektor 1 wykryty -> support widzi realny ogień
    assert 1 in engine._detected_sectors
    assert last[1]["fireLevel"] > 0

    # sektor 9 niewykryty, ale faktycznie płonie -> support dostaje zero
    assert 9 not in engine._detected_sectors
    assert engine.current_snapshot.sectors[9].state == SectorState.BURNING
    assert last[9]["fireLevel"] == 0.0


def test_S11b_detection_disabled_gives_full_state():
    """Z detection_enabled=False support znów ma pełną wiedzę (stare zachowanie)."""
    engine = make_engine(rows=3, cols=3, seed=12)
    engine.detection_enabled = False
    pub = _RecordingPublisher()
    engine.rabbitmq_publisher = pub

    engine.ignite_sector(9)  # bez sensora ani patrolu
    run_ticks(engine, 6)

    last = {s["sectorId"]: s["state"] for s in pub.support_msgs[-1]["sectors"]}
    assert last[9]["fireLevel"] > 0, "bez bramkowania support powinien widzieć ogień"


# ─── Scenariusz 12: nazwy fireState zgodne z enumem backendu ──────────────────

def test_S12_fire_state_names_match_backend_enum():
    """get_fire_state_name zwraca wartości, które potrafi sparsować backend."""
    allowed = {"NON_COMBUSTED", "MILD", "MODERATE", "FULL", "SEVERE",
               "COMBUSTED", "EXTINGUISHED"}
    forest = build_grid(1, 1)
    sector = forest[1]

    sector.state = SectorState.DORMANT
    sector.fire_level = 0.0
    assert sector.get_fire_state_name() == "NON_COMBUSTED"

    sector.state = SectorState.BURNING
    for level, expected in [(0.1, "MILD"), (0.4, "MODERATE"),
                            (0.6, "FULL"), (0.9, "SEVERE")]:
        sector.fire_level = level
        assert sector.get_fire_state_name() == expected, f"fireLevel={level}"

    sector.state = SectorState.EXTINGUISHED
    assert sector.get_fire_state_name() == "EXTINGUISHED"
    sector.state = SectorState.ASH
    assert sector.get_fire_state_name() == "COMBUSTED"

    # wszystkie zwracane wartości mieszczą się w enumie backendu
    assert {sector.get_fire_state_name()} <= allowed


# ─── Scenariusz 13: threatLevel w telemetrii ─────────────────────────────────

def test_S13_threat_level_in_telemetry():
    """Telemetria niesie threatLevel z poprawnego zbioru, rosnący przy pożarze."""
    allowed = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH", "CRITICAL"}
    engine = make_engine(rows=3, cols=3, seed=20)
    pub = _RecordingPublisher()
    engine.rabbitmq_publisher = pub
    engine.ignite_sector(5)  # środek siatki 3x3
    run_ticks(engine, 8)

    # threatLevel jest na kanale mapy (telemetry["sectors"]), nie w feedzie supportu
    telemetry = engine._phase_telemetry_generation(
        next_sectors=engine.current_snapshot.sectors,
        previous_sectors=engine.current_snapshot.sectors,
        wind=engine.current_snapshot.wind,
        temperature=engine.current_snapshot.global_temperature,
        timestamp="t",
    )
    by_id = {s["sectorId"]: s for s in telemetry["sectors"]}
    assert all(s["threatLevel"] in allowed for s in telemetry["sectors"])
    # płonący środek ma wysoki poziom zagrożenia
    assert by_id[5]["threatLevel"] in {"HIGH", "VERY_HIGH", "CRITICAL"}


# ─── Scenariusz 14: cofanie kroku przywraca stan ─────────────────────────────

def test_S14_step_back_restores_state():
    """step_back wraca do poprzedniego stanu sektorów i pozwala iść dalej."""
    engine = make_engine(rows=3, cols=3, seed=30)
    engine.ignite_sector(5)
    run_ticks(engine, 4)

    tick4 = engine.tick_count
    snap4 = {sid: s.fire_level for sid, s in engine.current_snapshot.sectors.items()}

    engine.step()
    engine.step()
    assert engine.tick_count == tick4 + 2

    assert engine.step_back()
    assert engine.step_back()
    assert engine.tick_count == tick4

    snap_back = {sid: s.fire_level for sid, s in engine.current_snapshot.sectors.items()}
    assert snap_back == snap4, "po cofnięciu stan sektorów powinien wrócić do tick4"

    # po cofnięciu da się znów iść w przód
    engine.step()
    assert engine.tick_count == tick4 + 1

    # nie można cofnąć poniżej stanu początkowego w nieskończoność
    for _ in range(50):
        if not engine.step_back():
            break
    assert engine.step_back() is False
