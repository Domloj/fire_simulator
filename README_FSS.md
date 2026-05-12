# 1. Cel systemu

FFSim (Fire Forest Simulation) jest deterministycznym silnikiem symulacyjnym odpowiedzialnym za:

- symulację rozprzestrzeniania się pożaru lasu,
- symulację działań agentów terenowych,
- generowanie telemetrii środowiskowej,
- publikację zdarzeń do systemu wsparcia (FFSup),
- wykonywanie rozkazów otrzymywanych z FFBackend.

FFSim NIE podejmuje decyzji strategicznych.

System:

- nie implementuje LLM,
- nie implementuje algorytmów optymalizacji,
- nie przydziela autonomicznie brygad,
- nie planuje strategii gaszenia.

FFSim pełni wyłącznie rolę:

- deterministycznego modelu świata,
- generatora danych telemetrycznych,
- wykonawcy rozkazów.

---

# 2. Wymagania architektoniczne

## 2.1 Determinizm

Dla:

- identycznego seeda,
- identycznej konfiguracji,
- identycznej kolejności rozkazów,

symulacja MUSI generować identyczny przebieg.

Deterministyczność obejmuje:

- propagację pożaru,
- ewolucję środowiska,
- ruch agentów,
- publikację telemetrii,
- generowanie szumu sensorów.

---

## 2.2 Immutable Tick Model

Każdy tick operuje wyłącznie na snapshotcie poprzedniego stanu.

Model:

```
currentState -> nextState
```

Modyfikacje wykonywane są wyłącznie na `nextState`.

Zabronione:

- modyfikacje in-place,
- side effecty między sektorami,
- wpływ zmian z ticka t+1 na inne sektory w tym samym ticku.

---

## 2.3 Jedno źródło losowości

Cała symulacja korzysta z jednego generatora RNG.

Zabronione:

- Math.random(),
- lokalne RNG,
- niedeterministyczne źródła czasu.

Stan RNG jest częścią snapshotu symulacji.

---

# 3. Architektura systemu

## 3.1 Moduły

```
+----------------------+| FFBackend            |+----------+-----------+           |           | REST           v+----------------------+| FFSim                ||----------------------|| Simulation Engine    || Fire Propagation     || Agent Engine         || Environment Engine   || Sensor Engine        || Command Validator    || Telemetry Publisher  || Snapshot Manager     |+----------+-----------+           |           | RabbitMQ           v+----------------------+| FFSup                |+----------------------+
```

---

# 4. Główny cykl symulacji

## 4.1 Tick lifecycle

Każdy tick przebiega w następującej kolejności:

```
1. Snapshot currentState -> previousState2. Propagacja pożaru3. Aktualizacja agentów4. Aktualizacja środowiska5. Generacja telemetrii6. Publikacja RabbitMQ7. Commit nextState
```

---

## 4.2 Zasady wykonania ticka

### Faza 1 — Snapshot

Tworzona jest niemodyfikowalna kopia:

```
previousState
```

---

### Faza 2 — Propagacja pożaru

Na podstawie `previousState`:

- obliczane są nowe zapłony,
- aktualizowane są poziomy ognia,
- aktualizowane jest paliwo,
- wyznaczane są sektory wypalone.

Wszystkie zmiany trafiają do:

```
nextState
```

---

### Faza 3 — Aktualizacja agentów

Agenci:

- zmieniają pozycję,
- zmieniają stan FSM,
- wykonują akcje,
- zwiększają extinguishLevel.

Efekty agentów stają się widoczne od kolejnego ticka.

---

### Faza 4 — Aktualizacja środowiska

Aktualizacja:

- wiatru,
- temperatury globalnej,
- wilgotności globalnej.

---

### Faza 5 — Generacja telemetrii

Tworzone są:

- telemetry sektorów,
- telemetry sensorów,
- telemetry agentów,
- eventy pożarowe.

---

### Faza 6 — Publikacja

Publikacja do RabbitMQ.

---

### Faza 7 — Commit

```
currentState = nextState
```

---

# 5. Model L-systemowy

## 5.1 Alfabet

| Symbol | Znaczenie            |
| ------ | -------------------- |
| F      | sektor niepalący się |
| B      | sektor płonący       |
| A      | sektor wypalony      |
| W      | sektor niepalny      |

---

## 5.2 Parametry sektora

Każdy sektor posiada:

| Parametr        | Zakres |
| --------------- | ------ |
| moisture        | [0,1]  |
| fuel            | [0,1]  |
| fireLevel       | [0,1]  |
| burnLevel       | [0,1]  |
| extinguishLevel | [0,1]  |
| temperature     | ℝ      |
| sectorType      | enum   |

---

## 5.3 Sąsiedztwo

Model wykorzystuje sąsiedztwo 4-kierunkowe:

- góra,
- dół,
- lewo,
- prawo.

Brakujący sąsiad:

- nie wpływa na propagację.

---

# 6. Model propagacji pożaru

## 6.1 Reguła zapłonu

Zapłon może wystąpić wyłącznie gdy:

- istnieje płonący sąsiad,
- sektor posiada paliwo,
- sektor nie jest WATER lub ASH.

Prawdopodobieństwo zapłonu:

pign=clamp(0,1,f(1−m)(1+α∣w⃗∣cos⁡θ)⋅ℓneighbor⋅(1+β(T−Tref)))p*{ign}=clamp\left(0,1,f(1-m)(1+\alpha |\vec{w}|\cos\theta)\cdot \ell*{neighbor}\cdot (1+\beta(T-T\_{ref}))\right)pign​=clamp(0,1,f(1−m)(1+α∣w∣cosθ)⋅ℓneighbor​⋅(1+β(T−Tref​)))

gdzie:

| Symbol    | Znaczenie                       |
| --------- | ------------------------------- |
| f         | ilość paliwa                    |
| m         | wilgotność                      |
| w         | wiatr                           |
| θ         | kierunek względem wiatru        |
| ℓneighbor | intensywność sąsiedniego pożaru |
| T         | temperatura                     |
| α         | wpływ wiatru                    |
| β         | wpływ temperatury               |

---

## 6.2 Rozwój pożaru

Poziom ognia rośnie zgodnie z:

ℓt+1=ℓt+spreadRate⋅windMultiplier⋅sectorMultiplier\ell\_{t+1}=\ell_t+spreadRate\cdot windMultiplier\cdot sectorMultiplierℓt+1​=ℓt​+spreadRate⋅windMultiplier⋅sectorMultiplier

---

## 6.3 Zużycie paliwa

ft+1=ft−fireLevel⋅fuelConsumptionRatef\_{t+1}=f_t-fireLevel\cdot fuelConsumptionRateft+1​=ft​−fireLevel⋅fuelConsumptionRate

---

## 6.4 Wypalenie

Jeżeli:

```
fuel <= 0
```

to:

```
sector -> ASH
```

---

## 6.5 Gaszenie

Brygady zwiększają:

```
extinguishLevel += extinguishRate
```

Jeżeli:

```
extinguishLevel >= 1
```

to:

```
sector -> EXTINGUISHED
```

---

# 7. Model środowiska

## 7.1 Globalny model wiatru

Wiatr posiada:

- speed,
- direction.

Wiatr jest globalny dla całej mapy.

---

## 7.2 Ewolucja środowiska

Zmiany środowiskowe wykonywane są:

- raz na tick,
- deterministycznie względem RNG.

---

# 8. Model agentów

# 8.1 ForesterPatrol FSM

```
AVAILABLE    ↓TRAVELLING    ↓PATROLLING    ↓TRAVELLING_TO_BASE    ↓AVAILABLE
```

---

## 8.2 FireBrigade FSM

```
AVAILABLE    ↓TRAVELLING    ↓EXTINGUISHING    ↓TRAVELLING_TO_BASE    ↓AVAILABLE
```

---

# 8.3 Zasady FSM

Dozwolone są wyłącznie zdefiniowane przejścia.

Przykład:

NIEPOPRAWNE:

```
AVAILABLE -> EXTINGUISHING
```

POPRAWNE:

```
AVAILABLE -> TRAVELLING -> EXTINGUISHING
```

---

# 9. Obsługa rozkazów

## 9.1 Pipeline walidacji

Każdy rozkaz przechodzi:

```
1. Schema validation2. Agent existence validation3. Sector existence validation4. Agent type validation5. FSM transition validation6. Command enqueue
```

---

## 9.2 Obsługiwane rozkazy

| Endpoint           | Opis               |
| ------------------ | ------------------ |
| /orderForestPatrol | rozkaz dla leśnika |
| /orderFireBrigade  | rozkaz dla brygady |
| /assignBrigades    | przypisanie brygad |

---

# 10. Telemetria

## 10.1 Wspólny format

Każda wiadomość telemetryczna posiada:

```
{  "simulationId": "uuid",  "tick": 1523,  "timestamp": "2026-05-12T18:00:00Z",  "payload": {}}
```

---

# 10.2 Telemetria sektorów

Routing key:

```
simulation.telemetry.map.sector_state
```

Payload:

```
{  "sectorId": 12,  "fireLevel": 0.35,  "burnLevel": 0.1,  "extinguishLevel": 0.0,  "fireState": "MODERATE"}
```

---

# 10.3 Telemetria agentów

Routing keys:

```
simulation.telemetry.agents.forestersimulation.telemetry.agents.fire_brigade
```

---

# 10.4 Eventy

Routing keys:

```
simulation.events.fire_startedsimulation.events.fire_extinguishedsimulation.events.agent_arrivedsimulation.events.command_received
```

---

# 11. RabbitMQ Publishing Policy

| Kanał             | Częstotliwość |
| ----------------- | ------------- |
| sector_state_fast | każdy tick    |
| agents_batch      | każdy tick    |
| sensors           | każdy tick    |
| fire_events       | event-driven  |
| snapshot          | on-demand     |

---

# 12. Tryb eksperymentalny

## 12.1 Seed

Symulacja może zostać uruchomiona:

```
{  "seed": 12345}
```

---

## 12.2 Snapshot

Endpoint:

```
GET /snapshot
```

Zwraca:

- stan sektorów,
- stan agentów,
- stan RNG,
- stan środowiska,
- aktualny tick.

---

## 12.3 Single Step

```
POST /step
```

Wykonuje dokładnie jeden tick.

---

# 13. Logging i metryki

## 13.1 Logi debugowe

Zapisywane:

- komendy,
- zmiany stanów,
- błędy FSM,
- zdarzenia pożarowe.

---

## 13.2 Metryki eksperymentalne

Minimalny zestaw:

| Metryka                 |
| ----------------------- |
| tick                    |
| burningSectors          |
| burnedSectors           |
| activeBrigades          |
| activeForesters         |
| ignitionToDetectionTime |
| commandToExtinguishTime |

---

# 14. Scenariusze testowe

Minimalne scenariusze:

| Nazwa                   |
| ----------------------- |
| single_fire_no_wind     |
| single_fire_strong_wind |
| multi_fire              |
| insufficient_brigades   |
| no_foresters            |

---

# 15. Założenia uproszczające

System świadomie NIE modeluje:

- realistycznej fizyki spalania,
- topografii terenu,
- lokalnych wiatrów,
- regeneracji lasu,
- rzeczywistej hydrodynamiki gaszenia,
- dokładnej kinematyki ruchu pojazdów.

Celem systemu jest:

- testowanie systemu wsparcia,
- generowanie powtarzalnych scenariuszy,
- dostarczanie telemetrii,
- walidacja logiki dispatchingu.
