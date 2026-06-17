"""
Agent manager for FFSim — ForesterPatrol and FireBrigade.

Spec section 4:
  Leśnik:   AVAILABLE → TRAVELLING → PATROLLING   → AVAILABLE
  Brygada:  AVAILABLE → TRAVELLING → EXTINGUISHING → AVAILABLE

Zasady:
- Zmiana stanu następuje natychmiast po odebraniu rozkazu (ta sama faza ticku).
- Czas dojazdu (travelTime) jest stały i konfigurowalny [ticki].
- Brygada w stanie EXTINGUISHING zwiększa extinguishLevel sektora
  o extinguishRate na każdy krok.
- Leśnik w zapłoniętym sektorze jest automatycznie wycofywany (auto-withdraw).
- Wszystkie obiekty mają clone() — wymagane przez immutable tick model.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.models.sector import Sector, SectorState


# ─── Enumeracje ───────────────────────────────────────────────────────────────

class AgentState(Enum):
    AVAILABLE     = "AVAILABLE"
    TRAVELLING    = "TRAVELLING"
    PATROLLING    = "PATROLLING"
    EXTINGUISHING = "EXTINGUISHING"


class AgentAction(Enum):
    """Ostatni rozkaz otrzymany z support — publikowany w telemetrii."""
    NONE        = "NONE"
    PATROL      = "PATROL"
    EXTINGUISH  = "EXTINGUISH"
    GO_TO_BASE  = "GO_TO_BASE"


class AgentEventType(Enum):
    FORESTER_DISPATCHED      = "FORESTER_DISPATCHED"
    FORESTER_ARRIVED         = "FORESTER_ARRIVED"
    FORESTER_RETURNED        = "FORESTER_RETURNED"
    FORESTER_AUTO_WITHDRAWN  = "FORESTER_AUTO_WITHDRAWN"
    BRIGADE_DISPATCHED       = "BRIGADE_DISPATCHED"
    BRIGADE_ARRIVED          = "BRIGADE_ARRIVED"
    BRIGADE_RETURNED         = "BRIGADE_RETURNED"


# ─── Konfiguracja ─────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """Parametry konfiguracyjne modelu agentów."""
    travel_time: int   = 5     # [ticki] stały czas dojazdu do sektora
    # 0.10 daje jednej brygadzie ~10 ticków na ugaszenie — mieści się w czasie
    # wypalania sektora (~23 ticki), więc pojedyncza reakcja ma sens. Przy 0.05
    # brygada zawsze przegrywała z wypalaniem (20 ticków > 18).
    extinguish_rate: float = 0.10  # przyrost extinguishLevel na brygadę na krok

    # Proaktywne patrolowanie: leśnicy sami objeżdżają teren, nie czekając na
    # rozkaz z supportu. Bez tego detekcja zależy wyłącznie od czujników i pożar
    # bywa wykryty z dużym opóźnieniem.
    proactive_patrol: bool = True
    patrol_dwell: int = 2          # [ticki] postój w sektorze zanim leśnik ruszy dalej


# ─── Lokalizacja ──────────────────────────────────────────────────────────────

@dataclass
class Location:
    lon: float
    lat: float

    def distance_to(self, other: "Location") -> float:
        """Przybliżona odległość euklidesowa (wystarczająca do interpolacji)."""
        return math.sqrt((self.lon - other.lon) ** 2 + (self.lat - other.lat) ** 2)

    def interpolate(self, target: "Location", t: float) -> "Location":
        """Liniowa interpolacja między self a target dla t ∈ [0, 1]."""
        t = max(0.0, min(1.0, t))
        return Location(
            lon=self.lon + (target.lon - self.lon) * t,
            lat=self.lat + (target.lat - self.lat) * t,
        )

    def clone(self) -> "Location":
        return Location(lon=self.lon, lat=self.lat)

    def to_dict(self) -> Dict[str, float]:
        return {"lon": self.lon, "lat": self.lat}

    @staticmethod
    def from_dict(d: Dict[str, float]) -> "Location":
        # rozkazy z backendu/frontendu używają longitude/latitude,
        # telemetria wewnętrzna lon/lat — akceptujemy oba
        lon = d.get("lon", d.get("longitude"))
        lat = d.get("lat", d.get("latitude"))
        return Location(lon=float(lon), lat=float(lat))


# ─── Zdarzenia agentów ────────────────────────────────────────────────────────

@dataclass
class AgentEvent:
    tick: int
    event_type: AgentEventType
    agent_id: int
    sector_id: Optional[int] = None
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "sector_id": self.sector_id,
            "detail": self.detail,
        }


# ─── Wynik walidacji rozkazu ─────────────────────────────────────────────────

@dataclass
class OrderResult:
    success: bool
    error_code: Optional[str] = None
    message: Optional[str] = None

    @staticmethod
    def ok() -> "OrderResult":
        return OrderResult(success=True)

    @staticmethod
    def error(code: str, msg: str) -> "OrderResult":
        return OrderResult(success=False, error_code=code, message=msg)


# ─── Bazowa klasa agenta ──────────────────────────────────────────────────────

@dataclass
class Agent:
    """Bazowy agent symulacji."""

    agent_id: int
    base_location: Location          # lokalizacja bazy (stała)

    state: AgentState        = AgentState.AVAILABLE
    current_action: AgentAction = AgentAction.NONE
    current_location: Location = field(default=None)   # type: ignore
    current_sector_id: Optional[int] = None

    # Dane podróży (aktywne gdy state == TRAVELLING)
    target_sector_id: Optional[int]   = None
    target_location: Optional[Location] = None
    travel_ticks_remaining: int        = 0
    travel_ticks_total: int            = 0
    travel_origin: Optional[Location]  = None  # punkt startowy podróży

    def __post_init__(self):
        if self.current_location is None:
            self.current_location = self.base_location.clone()

    # ------------------------------------------------------------------
    # Obliczenie bieżącej lokalizacji
    # ------------------------------------------------------------------

    def get_current_location(self) -> Location:
        """
        Zwraca bieżącą lokalizację agenta.

        Dla TRAVELLING: interpolacja liniowa między travel_origin a target_location
        na podstawie postępu podróży.
        """
        if (self.state == AgentState.TRAVELLING
                and self.travel_origin is not None
                and self.target_location is not None
                and self.travel_ticks_total > 0):
            elapsed = self.travel_ticks_total - self.travel_ticks_remaining
            t = elapsed / self.travel_ticks_total
            return self.travel_origin.interpolate(self.target_location, t)
        return self.current_location

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def clone(self) -> "Agent":
        return copy.deepcopy(self)

    def to_dict(self) -> Dict[str, Any]:
        loc = self.get_current_location()
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "current_action": self.current_action.value,
            "location": loc.to_dict(),
            "sector_id": self.current_sector_id,
            "travel_ticks_remaining": self.travel_ticks_remaining,
        }


# ─── Konkretne typy agentów ───────────────────────────────────────────────────

@dataclass
class ForesterPatrol(Agent):
    """
    Leśnik patrolujący.

    Cykl życia: AVAILABLE → TRAVELLING → PATROLLING → AVAILABLE
    - Prowadzi dozór w sektorze NON_COMBUSTED.
    - Automatycznie wycofywany gdy sektor zapłonie.
    """

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["forester_patrol_id"] = self.agent_id
        return d


@dataclass
class FireBrigade(Agent):
    """
    Brygada gaśnicza.

    Cykl życia: AVAILABLE → TRAVELLING → EXTINGUISHING → AVAILABLE
    - Każdy krok w EXTINGUISHING zwiększa extinguishLevel sektora
      o extinguishRate (per brygada).
    """

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["fire_brigade_id"] = self.agent_id
        return d


# ─── Manager agentów ─────────────────────────────────────────────────────────

class AgentManager:
    """
    Zarządza wszystkimi agentami symulacji.

    Odpowiedzialności:
    - Obsługa rozkazów z support (apply_order).
    - Aktualizacja stanów agentów w fazie 2 ticku (process_tick).
    - Automatyczne wycofywanie leśników z płonących sektorów.
    - Efekt gaszenia (extinguishLevel) na sektorach.
    - Snapshot semantics (clone / to_dict).
    """

    def __init__(self,
                 foresters: Optional[Dict[int, ForesterPatrol]] = None,
                 brigades: Optional[Dict[int, FireBrigade]] = None,
                 config: Optional[AgentConfig] = None):
        self.foresters: Dict[int, ForesterPatrol] = foresters or {}
        self.brigades:  Dict[int, FireBrigade]    = brigades  or {}
        self.config = config or AgentConfig()

        # Stan proaktywnego patrolowania: kiedy ostatnio każdy sektor był
        # obserwowany przez patrol oraz ile ticków dany leśnik stoi w sektorze.
        self._sector_last_patrolled: Dict[int, int] = {}
        self._patrol_dwell: Dict[int, int] = {}
        # Leśnicy aktualnie patrolujący autonomicznie. Rozkaz z supportu odbiera
        # leśnika z tego zbioru, więc roaming nie nadpisuje decyzji supportu.
        self._autonomous_patrol: set = set()

    # ------------------------------------------------------------------
    # Inicjalizacja agentów z konfiguracji mapy
    # ------------------------------------------------------------------

    def register_forester(self, forester_id: int, base_location: Location) -> None:
        """Rejestruje nowego leśnika (wywołać przy starcie symulacji)."""
        self.foresters[forester_id] = ForesterPatrol(
            agent_id=forester_id,
            base_location=base_location,
        )

    def register_brigade(self, brigade_id: int, base_location: Location) -> None:
        """Rejestruje nową brygadę (wywołać przy starcie symulacji)."""
        self.brigades[brigade_id] = FireBrigade(
            agent_id=brigade_id,
            base_location=base_location,
        )

    # ------------------------------------------------------------------
    # Faza 2 ticku — aktualizacja agentów
    # ------------------------------------------------------------------

    def process_tick(self,
                     next_sectors: Dict[int, "Sector"],
                     previous_sectors: Dict[int, "Sector"],
                     current_tick: int) -> List[AgentEvent]:
        """
        Przetwarza wszystkich agentów w fazie 2 ticku.

        Kolejność operacji:
        1. Wykrycie nowych zapłonów → auto-withdraw leśników.
        2. Odliczanie czasu podróży i obsługa przybycia.
        3. Efekt gaszenia brygad w EXTINGUISHING.

        Args:
            next_sectors:     Sektory po propagacji pożaru (faza 1) — modyfikowane tu.
            previous_sectors: Stan sektorów z poprzedniego ticku (tylko do odczytu).
            current_tick:     Numer bieżącego ticku.

        Returns:
            Lista zdarzeń agentów wygenerowanych w tym ticku.
        """
        events: List[AgentEvent] = []

        # 1. Auto-withdraw leśników z nowo zapłoniętych sektorów
        events += self._auto_withdraw_foresters(next_sectors, previous_sectors, current_tick)

        # 2. Podróż — odlicz tick; obsłuż przybycie
        for forester in self.foresters.values():
            events += self._tick_travel(forester, next_sectors, current_tick)

        for brigade in self.brigades.values():
            events += self._tick_travel(brigade, next_sectors, current_tick)

        # 3. Efekt gaszenia
        events += self._apply_extinguishing(next_sectors, current_tick)

        # 4. Proaktywne patrolowanie — leśnicy sami objeżdżają sektory, dzięki
        #    czemu wykrywają pożar wcześnie, nie czekając na rozkaz z supportu.
        if self.config.proactive_patrol:
            events += self._assign_proactive_patrols(next_sectors, current_tick)

        return events

    def _assign_proactive_patrols(self,
                                  next_sectors: Dict[int, "Sector"],
                                  current_tick: int) -> List[AgentEvent]:
        """
        Autonomiczne patrolowanie leśników.

        Bezczynny leśnik (AVAILABLE) dostaje cel, a patrolujący po kilku tickach
        rusza dalej, żeby pokrywać teren zamiast tkwić w jednym sektorze. Cel to
        sektor najdawniej obserwowany przez patrol, więc patrole rozchodzą się po
        mapie i wykrywają pożar zanim ten dorośnie do czujnika.
        """
        events: List[AgentEvent] = []

        # Odśwież czas obserwacji sektorów aktualnie patrolowanych i licz postój.
        for forester in self.foresters.values():
            if (forester.state == AgentState.PATROLLING
                    and forester.current_sector_id is not None):
                self._sector_last_patrolled[forester.current_sector_id] = current_tick
                self._patrol_dwell[forester.agent_id] = (
                    self._patrol_dwell.get(forester.agent_id, 0) + 1
                )
            else:
                self._patrol_dwell[forester.agent_id] = 0

        # Sektory zajęte przez innych leśników (cel albo aktualnie patrolowany) —
        # nie chcemy, by kilku zbiegło się na ten sam. Zbieramy też ich
        # lokalizacje, żeby nowe cele wybierać z dala od nich (rozpraszanie).
        occupied: set = set()
        claimed_locations: List[Location] = []
        for f in self.foresters.values():
            for sid in (f.target_sector_id,
                        f.current_sector_id if f.state == AgentState.PATROLLING else None):
                if sid is None:
                    continue
                occupied.add(sid)
                s = next_sectors.get(sid)
                if s is not None and s.longitude is not None and s.latitude is not None:
                    claimed_locations.append(Location(lon=s.longitude, lat=s.latitude))

        for forester in self.foresters.values():
            idle = forester.state == AgentState.AVAILABLE
            # Re-roaming tylko dla leśników, których support nie przejął.
            done_dwelling = (
                forester.state == AgentState.PATROLLING
                and forester.agent_id in self._autonomous_patrol
                and self._patrol_dwell.get(forester.agent_id, 0) >= self.config.patrol_dwell
            )
            if not (idle or done_dwelling):
                continue

            target_id = self._pick_patrol_target(
                forester, next_sectors, occupied, claimed_locations
            )
            if target_id is None:
                continue

            sector = next_sectors[target_id]
            forester.state = AgentState.TRAVELLING
            forester.current_action = AgentAction.PATROL
            forester.travel_origin = forester.get_current_location()
            forester.target_sector_id = target_id
            forester.target_location = Location(lon=sector.longitude, lat=sector.latitude)
            forester.travel_ticks_total = self.config.travel_time
            forester.travel_ticks_remaining = self.config.travel_time
            forester.current_sector_id = None
            self._patrol_dwell[forester.agent_id] = 0
            self._autonomous_patrol.add(forester.agent_id)
            occupied.add(target_id)  # kolejny leśnik w tym ticku już go nie wybierze
            claimed_locations.append(forester.target_location)  # następny wybierze z dala
            events.append(AgentEvent(
                tick=current_tick,
                event_type=AgentEventType.FORESTER_DISPATCHED,
                agent_id=forester.agent_id,
                sector_id=target_id,
                detail="proactive patrol",
            ))
        return events

    def _pick_patrol_target(self,
                            forester: "ForesterPatrol",
                            next_sectors: Dict[int, "Sector"],
                            occupied: set,
                            claimed_locations: List[Location]) -> Optional[int]:
        """
        Wybiera sektor do patrolowania: najdawniej obserwowany (nigdy = najstarszy),
        palny, nie płonący i nie zajęty przez innego leśnika.

        Remis wieku rozstrzyga rozpraszanie: preferujemy sektor jak najdalej od
        pozostałych patroli, żeby leśnicy rozeszli się po mapie zamiast zbiegać
        w jeden region. Dopiero na końcu liczy się krótki dojazd własny.
        """
        here = forester.get_current_location()
        best_id: Optional[int] = None
        best_key: Optional[Tuple[int, float, float]] = None

        for sid, sector in next_sectors.items():
            if sid in occupied:
                continue
            if sector.longitude is None or sector.latitude is None:
                continue
            if not sector.is_flammable():   # DORMANT, ma paliwo, nie woda
                continue
            loc = Location(lon=sector.longitude, lat=sector.latitude)
            last = self._sector_last_patrolled.get(sid, -1)   # nigdy widziany = -1
            # odległość do najbliższego innego patrolu — im większa, tym lepiej
            spread = min((loc.distance_to(o) for o in claimed_locations), default=float("inf"))
            own = here.distance_to(loc)
            # najstarszy → najdalej od innych (−spread rośnie) → najbliżej siebie
            key = (last, -spread, own)
            if best_key is None or key < best_key:
                best_key = key
                best_id = sid

        return best_id

    def _auto_withdraw_foresters(self,
                                  next_sectors: Dict[int, "Sector"],
                                  previous_sectors: Dict[int, "Sector"],
                                  current_tick: int) -> List[AgentEvent]:
        """
        Automatycznie wycofuje leśników z sektorów, które właśnie zapłonęły.

        Zapłon = sektor był DORMANT w poprzednim ticku, jest BURNING po fazie 1.
        Leśnik jest natychmiast kierowany do bazy (przerywa PATROLLING lub TRAVELLING).
        """
        from src.engine.models.sector import SectorState  # local import

        newly_ignited = {
            sid
            for sid, sector in next_sectors.items()
            if sector.state == SectorState.BURNING
            and previous_sectors.get(sid) is not None
            and previous_sectors[sid].state == SectorState.DORMANT
        }

        events = []
        for forester in self.foresters.values():
            if forester.current_sector_id in newly_ignited:
                forester.state = AgentState.TRAVELLING
                forester.current_action = AgentAction.GO_TO_BASE
                forester.target_sector_id = None
                forester.target_location = forester.base_location.clone()
                forester.travel_origin = forester.get_current_location()
                forester.travel_ticks_total = self.config.travel_time
                forester.travel_ticks_remaining = self.config.travel_time
                old_sector = forester.current_sector_id
                forester.current_sector_id = None
                events.append(AgentEvent(
                    tick=current_tick,
                    event_type=AgentEventType.FORESTER_AUTO_WITHDRAWN,
                    agent_id=forester.agent_id,
                    sector_id=old_sector,
                    detail="sector ignited",
                ))
        return events

    def _tick_travel(self,
                     agent: Agent,
                     next_sectors: Dict[int, "Sector"],
                     current_tick: int) -> List[AgentEvent]:
        """
        Odlicza jeden tick podróży. Przy dotarciu przełącza stan agenta.
        """
        if agent.state != AgentState.TRAVELLING:
            return []

        agent.travel_ticks_remaining -= 1

        if agent.travel_ticks_remaining > 0:
            return []  # nadal w drodze

        # ── Agent dotarł do celu ──────────────────────────────────────
        agent.current_location = (
            agent.target_location.clone()
            if agent.target_location else agent.base_location.clone()
        )

        # Powrót do bazy
        if agent.current_action == AgentAction.GO_TO_BASE:
            agent.state = AgentState.AVAILABLE
            agent.current_sector_id = None
            agent.target_sector_id = None
            agent.target_location = None

            if isinstance(agent, ForesterPatrol):
                return [AgentEvent(current_tick, AgentEventType.FORESTER_RETURNED,
                                   agent.agent_id)]
            else:
                return [AgentEvent(current_tick, AgentEventType.BRIGADE_RETURNED,
                                   agent.agent_id)]

        # Dotarcie do sektora docelowego
        agent.current_sector_id = agent.target_sector_id
        agent.target_sector_id = None
        agent.target_location = None

        if isinstance(agent, ForesterPatrol):
            agent.state = AgentState.PATROLLING
            return [AgentEvent(current_tick, AgentEventType.FORESTER_ARRIVED,
                               agent.agent_id, sector_id=agent.current_sector_id)]

        if isinstance(agent, FireBrigade):
            # Sprawdź czy sektor nadal płonie
            sector = next_sectors.get(agent.current_sector_id)
            if sector is not None and sector.state.value == "BURNING":
                agent.state = AgentState.EXTINGUISHING
            else:
                # Sektor już nie płonie — wróć do bazy
                agent.state = AgentState.TRAVELLING
                agent.current_action = AgentAction.GO_TO_BASE
                agent.target_location = agent.base_location.clone()
                agent.travel_origin = agent.current_location.clone()
                agent.travel_ticks_total = self.config.travel_time
                agent.travel_ticks_remaining = self.config.travel_time
            return [AgentEvent(current_tick, AgentEventType.BRIGADE_ARRIVED,
                               agent.agent_id, sector_id=agent.current_sector_id)]

        return []

    def _apply_extinguishing(self,
                              next_sectors: Dict[int, "Sector"],
                              current_tick: int) -> List[AgentEvent]:
        """
        Wszystkie brygady w EXTINGUISHING zwiększają extinguishLevel sektora.

        Efekt kumulatywny: wiele brygad w tym samym sektorze działa addytywnie.
        """
        from src.engine.models.sector import SectorState  # local import

        events = []
        brigades_per_sector: Dict[int, int] = {}

        for brigade in self.brigades.values():
            if (brigade.state == AgentState.EXTINGUISHING
                    and brigade.current_sector_id is not None):
                brigades_per_sector[brigade.current_sector_id] = (
                    brigades_per_sector.get(brigade.current_sector_id, 0) + 1
                )

        for sector_id, count in brigades_per_sector.items():
            sector = next_sectors.get(sector_id)
            if sector is None or not sector.is_burning():
                # Sektor już nie płonie — odwołaj brygady
                self._recall_brigades_from(sector_id, current_tick, events)
                continue

            sector.extinguish_level = min(
                1.0,
                sector.extinguish_level + self.config.extinguish_rate * count
            )

        return events

    def _recall_brigades_from(self,
                               sector_id: int,
                               current_tick: int,
                               events: List[AgentEvent]) -> None:
        """Odwołuje wszystkie brygady z sektora, który przestał płonąć."""
        for brigade in self.brigades.values():
            if brigade.current_sector_id == sector_id:
                # Pozycję wyjściową bierzemy ZANIM zmienimy stan i cel. Inaczej
                # get_current_location() (stan już TRAVELLING, cel = baza, a stare
                # travel_ticks z remaining=0 dają t=1.0) zwróciłoby od razu bazę,
                # więc travel_origin = baza i brygada teleportuje się do swojej
                # bazy zamiast płynnie z niej wracać.
                origin = brigade.get_current_location()
                brigade.state = AgentState.TRAVELLING
                brigade.current_action = AgentAction.GO_TO_BASE
                brigade.target_sector_id = None
                brigade.target_location = brigade.base_location.clone()
                brigade.travel_origin = origin
                brigade.travel_ticks_total = self.config.travel_time
                brigade.travel_ticks_remaining = self.config.travel_time
                brigade.current_sector_id = None
                events.append(AgentEvent(
                    tick=current_tick,
                    event_type=AgentEventType.BRIGADE_RETURNED,
                    agent_id=brigade.agent_id,
                    sector_id=sector_id,
                    detail="sector no longer burning",
                ))

    # ------------------------------------------------------------------
    # Obsługa rozkazów z support
    # ------------------------------------------------------------------

    def apply_forester_order(self,
                             order: Dict[str, Any],
                             sectors: Dict[int, "Sector"]) -> OrderResult:
        """
        Przetwarza rozkaz dla leśnika.

        Oczekiwany format:
            { "foresterPatrolId": 3,
              "action": "PATROL" | "GO_TO_BASE",
              "location": { "lon": ..., "lat": ... },
              "timestamp": "..." }

        Walidacja per spec sekcja 5 (pełna walidacja w kroku 2 — REST API).
        """
        # ── Walidacja podstawowa ─────────────────────────────────────
        forester_id = order.get("foresterPatrolId")
        if forester_id is None:
            return OrderResult.error("MISSING_FIELD", "Brak pola foresterPatrolId")

        forester = self.foresters.get(forester_id)
        if forester is None:
            return OrderResult.error(
                "UNKNOWN_AGENT",
                f"Leśnik foresterPatrolId={forester_id} nie istnieje"
            )

        action = order.get("action")
        if action not in ("PATROL", "GO_TO_BASE"):
            return OrderResult.error(
                "INVALID_ACTION_FOR_AGENT_TYPE",
                f"Nieznana akcja '{action}' dla ForesterPatrol"
            )

        # Gdy patrol autonomiczny jest włączony, ignorujemy rozkazy PATROL z
        # zewnątrz. Support rekomenduje leśnikom słabe cele (heurystyka bez
        # tie-breakingu zbija ich w sektory o najniższych ID, czyli w jeden róg
        # mapy), a leśnikami i tak lepiej steruje rozproszony patrol symulatora.
        # GO_TO_BASE działa dalej, żeby auto-withdraw i odwołanie do bazy żyło.
        if action == "PATROL" and self.config.proactive_patrol:
            return OrderResult.ok()

        # Operator/support przejmuje sterowanie tym leśnikiem — autonomiczny
        # patrol przestaje go ruszać, dopóki nie wróci do bazy.
        self._autonomous_patrol.discard(forester_id)

        location_raw = order.get("location")
        if location_raw is None:
            return OrderResult.error("MISSING_FIELD", "Brak pola location")

        target_location = Location.from_dict(location_raw)
        target_sector_id = self._find_sector_by_location(target_location, sectors)

        # ── PATROL ───────────────────────────────────────────────────
        if action == "PATROL":
            if target_sector_id is None:
                return OrderResult.error(
                    "UNKNOWN_SECTOR",
                    f"Nie znaleziono sektora dla lokalizacji {location_raw}"
                )
            # Sprawdź czy sektor nie płonie (leśnik nie może być wysłany do płonącego)
            sector = sectors[target_sector_id]
            if sector.state.value == "BURNING":
                return OrderResult.error(
                    "SECTOR_ON_FIRE",
                    f"Sektor {target_sector_id} płonie — leśnik nie może tam być wysłany"
                )

            # Powtórzony rozkaz na ten sam sektor nie resetuje dojazdu
            # (auto-apply wysyła go co tick). Po dojechaniu target_sector_id
            # jest czyszczony, więc dla patrolującego porównujemy current.
            if forester.current_action == AgentAction.PATROL and (
                (forester.state == AgentState.TRAVELLING and
                 forester.target_sector_id == target_sector_id) or
                (forester.state == AgentState.PATROLLING and
                 forester.current_sector_id == target_sector_id)
            ):
                return OrderResult.ok()

            # Natychmiastowe przejście do TRAVELLING
            forester.state = AgentState.TRAVELLING
            forester.current_action = AgentAction.PATROL
            forester.travel_origin = forester.get_current_location()
            forester.target_sector_id = target_sector_id
            forester.target_location = target_location
            forester.travel_ticks_total = self.config.travel_time
            forester.travel_ticks_remaining = self.config.travel_time
            return OrderResult.ok()

        # ── GO_TO_BASE ────────────────────────────────────────────────
        if action == "GO_TO_BASE":
            if forester.state == AgentState.AVAILABLE:
                return OrderResult.ok()  # już w bazie — idempotentne

            forester.state = AgentState.TRAVELLING
            forester.current_action = AgentAction.GO_TO_BASE
            forester.travel_origin = forester.get_current_location()
            forester.target_sector_id = None
            forester.target_location = forester.base_location.clone()
            forester.travel_ticks_total = self.config.travel_time
            forester.travel_ticks_remaining = self.config.travel_time
            forester.current_sector_id = None
            return OrderResult.ok()

        return OrderResult.error("UNKNOWN_ACTION", f"Nieobsłużona akcja '{action}'")

    def apply_brigade_order(self,
                            order: Dict[str, Any],
                            sectors: Dict[int, "Sector"]) -> OrderResult:
        """
        Przetwarza rozkaz dla brygady gaśniczej.

        Oczekiwany format:
            { "fireBrigadeId": 1,
              "action": "EXTINGUISH" | "GO_TO_BASE",
              "fireState": "MODERATE",
              "location": { "lon": ..., "lat": ... },
              "timestamp": "..." }
        """
        # ── Walidacja podstawowa ─────────────────────────────────────
        brigade_id = order.get("fireBrigadeId")
        if brigade_id is None:
            return OrderResult.error("MISSING_FIELD", "Brak pola fireBrigadeId")

        brigade = self.brigades.get(brigade_id)
        if brigade is None:
            return OrderResult.error(
                "UNKNOWN_AGENT",
                f"Brygada fireBrigadeId={brigade_id} nie istnieje"
            )

        action = order.get("action")
        if action not in ("EXTINGUISH", "GO_TO_BASE"):
            return OrderResult.error(
                "INVALID_ACTION_FOR_AGENT_TYPE",
                f"Nieznana akcja '{action}' dla FireBrigade"
            )

        location_raw = order.get("location")
        if location_raw is None:
            return OrderResult.error("MISSING_FIELD", "Brak pola location")

        target_location = Location.from_dict(location_raw)
        target_sector_id = self._find_sector_by_location(target_location, sectors)

        # ── EXTINGUISH ────────────────────────────────────────────────
        if action == "EXTINGUISH":
            if target_sector_id is None:
                return OrderResult.error(
                    "UNKNOWN_SECTOR",
                    f"Nie znaleziono sektora dla lokalizacji {location_raw}"
                )
            sector = sectors[target_sector_id]
            if sector.state.value != "BURNING":
                return OrderResult.error(
                    "SECTOR_NOT_ON_FIRE",
                    f"Sektor {target_sector_id} nie płonie"
                )

            # Commitment brygady: jeśli już jedzie/gasi jakiś PŁONĄCY sektor,
            # ignorujemy przekierowanie. Support co tick poleca inny sektor
            # (front pożaru się przesuwa), więc bez tego brygada restartowałaby
            # dojazd co krok i nigdy by nie dojechała. Przyjmujemy nowy rozkaz
            # tylko gdy brygada jest wolna albo jej obecny cel już nie płonie.
            active_target = None
            if brigade.state == AgentState.TRAVELLING:
                active_target = brigade.target_sector_id
            elif brigade.state == AgentState.EXTINGUISHING:
                active_target = brigade.current_sector_id

            if (active_target is not None
                    and brigade.current_action == AgentAction.EXTINGUISH):
                active_sector = sectors.get(active_target)
                if active_sector is not None and active_sector.state.value == "BURNING":
                    # nadal zajęta sensownym celem — nie przerywamy
                    return OrderResult.ok()

            brigade.state = AgentState.TRAVELLING
            brigade.current_action = AgentAction.EXTINGUISH
            brigade.travel_origin = brigade.get_current_location()
            brigade.target_sector_id = target_sector_id
            brigade.target_location = target_location
            brigade.travel_ticks_total = self.config.travel_time
            brigade.travel_ticks_remaining = self.config.travel_time
            return OrderResult.ok()

        # ── GO_TO_BASE ────────────────────────────────────────────────
        if action == "GO_TO_BASE":
            if brigade.state == AgentState.AVAILABLE:
                return OrderResult.ok()

            brigade.state = AgentState.TRAVELLING
            brigade.current_action = AgentAction.GO_TO_BASE
            brigade.travel_origin = brigade.get_current_location()
            brigade.target_sector_id = None
            brigade.target_location = brigade.base_location.clone()
            brigade.travel_ticks_total = self.config.travel_time
            brigade.travel_ticks_remaining = self.config.travel_time
            brigade.current_sector_id = None
            return OrderResult.ok()

        return OrderResult.error("UNKNOWN_ACTION", f"Nieobsłużona akcja '{action}'")

    def apply_assign_brigades(self,
                              order: Dict[str, Any],
                              sectors: Dict[int, "Sector"]) -> OrderResult:
        """
        Przypisuje listę brygad do sektora (/assignBrigades).

        Oczekiwany format:
            { "sectorId": 14,
              "assignedBrigades": [1, 2, 3] }
        """
        sector_id = order.get("sectorId")
        if sector_id is None:
            return OrderResult.error("MISSING_FIELD", "Brak pola sectorId")

        if sector_id not in sectors:
            return OrderResult.error(
                "UNKNOWN_SECTOR",
                f"Sektor sectorId={sector_id} nie istnieje"
            )

        assigned_ids = order.get("assignedBrigades", [])
        if not assigned_ids:
            return OrderResult.error("MISSING_FIELD", "Lista assignedBrigades jest pusta")

        sector = sectors[sector_id]
        if sector.state.value != "BURNING":
            return OrderResult.error(
                "SECTOR_NOT_ON_FIRE",
                f"Sektor {sector_id} nie płonie"
            )

        # Pobierz lat/lon sektora
        if sector.latitude is None or sector.longitude is None:
            return OrderResult.error(
                "SECTOR_NO_LOCATION",
                f"Sektor {sector_id} nie ma zdefiniowanej lokalizacji"
            )
        target_loc = Location(lon=sector.longitude, lat=sector.latitude)

        errors = []
        for brigade_id in assigned_ids:
            brigade = self.brigades.get(brigade_id)
            if brigade is None:
                errors.append(f"fireBrigadeId={brigade_id} nie istnieje")
                continue
            if brigade.state not in (AgentState.AVAILABLE, AgentState.EXTINGUISHING):
                errors.append(f"fireBrigadeId={brigade_id} jest w stanie {brigade.state.value}")
                continue

            brigade.state = AgentState.TRAVELLING
            brigade.current_action = AgentAction.EXTINGUISH
            brigade.travel_origin = brigade.get_current_location()
            brigade.target_sector_id = sector_id
            brigade.target_location = target_loc.clone()
            brigade.travel_ticks_total = self.config.travel_time
            brigade.travel_ticks_remaining = self.config.travel_time

        if errors:
            return OrderResult.error(
                "PARTIAL_FAILURE",
                "Niektóre brygady pominięte: " + "; ".join(errors)
            )
        return OrderResult.ok()

    # ------------------------------------------------------------------
    # Pomocnicze
    # ------------------------------------------------------------------

    def _find_sector_by_location(self,
                                  location: Location,
                                  sectors: Dict[int, "Sector"]) -> Optional[int]:
        """
        Zwraca sectorId najbliższego sektora do podanej lokalizacji.

        Używa przybliżonej odległości euklidesowej na centroidach sektorów.
        Zwraca None jeśli żaden sektor nie ma zdefiniowanych współrzędnych.
        """
        best_id: Optional[int] = None
        best_dist = float("inf")

        for sid, sector in sectors.items():
            if sector.latitude is None or sector.longitude is None:
                continue
            dist = location.distance_to(Location(sector.longitude, sector.latitude))
            if dist < best_dist:
                best_dist = dist
                best_id = sid

        return best_id

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def clone(self) -> "AgentManager":
        """Deep copy managera — wymagane przez immutable tick model."""
        return copy.deepcopy(self)

    def to_dict(self) -> Dict[str, Any]:
        """Serializacja do JSON (używana przez /snapshot)."""
        return {
            "foresters": [f.to_dict() for f in self.foresters.values()],
            "brigades":  [b.to_dict() for b in self.brigades.values()],
        }

    # ------------------------------------------------------------------
    # Statystyki (logowanie per tick)
    # ------------------------------------------------------------------

    def get_active_count(self) -> int:
        """Liczba agentów nie będących w AVAILABLE (do logowania)."""
        return sum(
            1 for a in [*self.foresters.values(), *self.brigades.values()]
            if a.state != AgentState.AVAILABLE
        )

    def get_extinguishing_count(self) -> int:
        """Liczba brygad aktualnie gaszących."""
        return sum(
            1 for b in self.brigades.values()
            if b.state == AgentState.EXTINGUISHING
        )

    def __repr__(self) -> str:
        return (
            f"AgentManager("
            f"foresters={len(self.foresters)}, "
            f"brigades={len(self.brigades)}, "
            f"active={self.get_active_count()})"
        )