type Pos = { id: number; unitType?: string; state?: string; lng: number; lat: number; t: number; prev?: Pos };

type Subscriber = (positions: Map<string, Pos>) => void;

class AgentPositionController {
  private positions = new Map<string, Pos>();
  private subscribers = new Set<Subscriber>();
  private rafId: number | null = null;
  private running = false;

  // Normalize incoming unit type variants to canonical names used in the app
  private normalizeUnitType(t: string | null | undefined): string | null {
    if (!t) return null;
    const s = String(t).toLowerCase();
    if (s.includes('fire') || s.includes('brigade')) return 'fireBrigade';
    if (s.includes('forester') || s.includes('patrol') || s === 'forester') return 'foresterPatrol';
    return null;
  }

  // Debug helper: return a small sample of stored position keys
  public getKeySample(limit = 10) {
    return Array.from(this.positions.keys()).slice(0, limit);
  }

  public parseAndWriteRaw(raw: string): boolean {
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || !(parsed.type === 'agent_position' || parsed.type === 'agent_positions') || !Array.isArray(parsed.data)) {
        return false;
      }

      const now = Date.now();

      for (const p of parsed.data) {
        // Backend now sends: { id, longitude, latitude, unitType, timestamp }
        const id = Number(p.id ?? p.agentId ?? p.fireBrigadeId ?? p.foresterPatrolId ?? p.unitId);
        if (!Number.isFinite(id)) continue;
        
        let providedUnitType = (p.unitType ?? p.type ?? null) as string | null;
        if (!providedUnitType) {
          if (p.fireBrigadeId !== undefined && p.fireBrigadeId !== null) providedUnitType = 'fireBrigade';
          else if (p.foresterPatrolId !== undefined && p.foresterPatrolId !== null) providedUnitType = 'foresterPatrol';
        }

        // Normalize unitType variants (e.g., 'forester' -> 'foresterPatrol')
        let resolvedUnitType = this.normalizeUnitType(providedUnitType) ?? null;
        if (!resolvedUnitType) {
          if (this.positions.has(`fireBrigade:${id}`)) resolvedUnitType = 'fireBrigade';
          else if (this.positions.has(`foresterPatrol:${id}`)) resolvedUnitType = 'foresterPatrol';
        }
        const usedPrefix = resolvedUnitType ?? 'u';
        const key = `${usedPrefix}:${id}`;
        
        // Support both nested location objects and flat longitude/latitude fields
        let lng: number;
        let lat: number;
        if (p.location ?? p.locationDto ?? p.currentLocation) {
          const loc = p.location ?? p.locationDto ?? p.currentLocation;
          lng = Number(loc.longitude ?? loc.lon ?? loc[0] ?? p.longitude ?? p.lng ?? p.lon ?? p.x);
          lat = Number(loc.latitude ?? loc.lat ?? loc[1] ?? p.latitude ?? p.lat ?? p.y);
        } else {
          lng = Number(p.longitude ?? p.lng ?? p.lon ?? p.x);
          lat = Number(p.latitude ?? p.lat ?? p.y);
        }
        
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
        if (Math.abs(lng) < 1e-6 && Math.abs(lat) < 1e-6) continue;
        const prev = this.positions.get(key);
        const state = p.state ?? null;
        const initialPrev = prev ? prev : { id, unitType: resolvedUnitType ?? undefined, state: state ?? undefined, lng, lat, t: now - 50 } as Pos;
        this.positions.set(key, { id, unitType: resolvedUnitType ?? undefined, state: state ?? undefined, lng, lat, t: now, prev: initialPrev });

        // Sprzątamy tylko placeholder nieznanego typu (u:id) po rozpoznaniu typu.
        // NIE kasujemy drugiego realnego typu o tym samym id — brygady i patrole
        // mają nakładające się id (0..7), więc kasowanie "fireBrigade:0" przy
        // patrolu o id 0 usuwało brygadę z mapy (raz widać, potem znika).
        if (usedPrefix !== 'u') this.positions.delete(`u:${id}`);
      }

      if (this.subscribers.size > 0 && !this.running) {
        this.startLoop();
      }

      return true;
    } catch (e) {
      // parsing failed - ignore
      return false;
    }
  }

  public writeBatch(agents: Array<any>) {
    const now = Date.now();
    // Debug: log first batch to see what data format we're receiving
    if (agents.length > 0 && typeof window !== 'undefined') {
      // console.log('[AgentPositionController] writeBatch received', agents.length, 'agents. Sample:', agents[0]);
    }
    for (const p of agents) {
      const id = Number(p.fireBrigadeId ?? p.foresterPatrolId ?? p.id ?? p.unitId ?? p.agentId);
      if (!Number.isFinite(id)) continue;

      // Robust unitType inference - don't use falsy checks on numeric IDs (0 is valid ID)
      let rawUnitType: string | null = null;
      if (p.fireBrigadeId !== undefined && p.fireBrigadeId !== null) rawUnitType = 'fireBrigade';
      else if (p.foresterPatrolId !== undefined && p.foresterPatrolId !== null) rawUnitType = 'foresterPatrol';
      else rawUnitType = (p.unitType ?? p.type ?? null);

      const inferredUnitType = this.normalizeUnitType(rawUnitType) ?? rawUnitType ?? null;
      const key = `${inferredUnitType ?? 'u'}:${id}`;

      // Support both nested location objects and flat longitude/latitude fields
      let lng: number | undefined;
      let lat: number | undefined;

      if (p.location ?? p.locationDto ?? p.currentLocation) {
        const loc = p.location ?? p.locationDto ?? p.currentLocation;
        lng = Number(loc.longitude ?? loc.lon ?? loc[0]);
        lat = Number(loc.latitude ?? loc.lat ?? loc[1]);
      } else {
        lng = Number(p.longitude ?? p.lng ?? p.lon ?? (Array.isArray(p) ? p[0] : undefined));
        lat = Number(p.latitude ?? p.lat ?? p.y ?? (Array.isArray(p) ? p[1] : undefined));
      }

      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      if (Math.abs(lng) < 1e-6 && Math.abs(lat) < 1e-6) continue;

      const prev = this.positions.get(key);
      const state = p.state ?? null;
      const initialPrev = prev ? prev : { id, unitType: inferredUnitType ?? undefined, state: state ?? undefined, lng, lat, t: now - 50 } as Pos;
      this.positions.set(key, { id, unitType: inferredUnitType ?? undefined, state: state ?? undefined, lng, lat, t: now, prev: initialPrev });
      // Tylko placeholder nieznanego typu (u:id); NIE kasujemy drugiego realnego
      // typu o tym samym id — brygady i patrole mają nakładające się id (0..7).
      const resolvedPrefix = inferredUnitType ?? 'u';
      if (resolvedPrefix !== 'u') this.positions.delete(`u:${id}`);
    }

    if (this.subscribers.size > 0 && !this.running) {
      this.startLoop();
    }
  }

  private frameCount: number = 0;
  private lastFpsTimestamp: number = 0;
  private currentFps: number = 0;

  private startLoop() {
    if (this.running) return;
    this.running = true;
    this.lastFpsTimestamp = Date.now();
    this.frameCount = 0;
    // console.debug('[AgentPositionController] startLoop');

    const frame = () => {
      const now = Date.now();

      const snapshot = new Map<string, Pos>();
      for (const [key, pos] of this.positions.entries()) {
        if (!pos) continue;
        const prev = pos.prev;
        let lng = pos.lng;
        let lat = pos.lat;
        if (prev && typeof prev.t === 'number' && pos.t > prev.t) {
          const dtTotal = pos.t - prev.t;
          const dtNow = now - prev.t;
          let ratio = dtTotal > 0 ? dtNow / dtTotal : 1;
          if (ratio < 0) ratio = 0;
          if (ratio > 1) ratio = 1;
          lng = prev.lng + (pos.lng - prev.lng) * ratio;
          lat = prev.lat + (pos.lat - prev.lat) * ratio;
        }
        snapshot.set(key, { id: pos.id, unitType: pos.unitType, state: pos.state, lng, lat, t: now, prev: pos.prev });
      }

      // console.debug('[AgentPositionController] frame', { snapshotSize: snapshot.size, subscriberCount: this.subscribers.size });
      for (const cb of this.subscribers) {
        try {
          cb(snapshot);
        } catch (e) {
          // ignore subscriber errors
        }
      }

      this.frameCount++;
      if (now - this.lastFpsTimestamp >= 1000) {
        this.currentFps = this.frameCount;
        this.frameCount = 0;
        this.lastFpsTimestamp = now;
      }

      this.rafId = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame(frame) : null;
    };

    this.rafId = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame(frame) : null;
  }

  private stopLoop() {
    if (!this.running) return;
    // console.debug('[AgentPositionController] stopLoop');
    if (this.rafId) {
      try { cancelAnimationFrame(this.rafId); } catch (e) { /* ignore cancellation errors */ }
      this.rafId = null;
    }
    this.running = false;
  }

  public subscribe(cb: Subscriber) {
    this.subscribers.add(cb);
    // console.debug('[AgentPositionController] subscribe, subscriberCount:', this.subscribers.size);
    if (!this.running) this.startLoop();
    return () => { this.subscribers.delete(cb); 
      // console.debug('[AgentPositionController] unsubscribe, subscriberCount:', this.subscribers.size); if (this.subscribers.size === 0) this.stopLoop(); 
    };
  }

  public getPosition(id: number, unitType?: string) {
    const key = `${unitType ?? 'u'}:${id}`;
    return this.positions.get(key);
  }

  public getBufferSize() {
    return this.positions.size;
  }

  public getFps() {
    return this.currentFps;
  }

  public getPositionsSnapshot() {
    return new Map(this.positions);
  }

  public clear() {
    this.positions.clear();
  }
}

export const agentPositionController = new AgentPositionController();
export type { Pos };
