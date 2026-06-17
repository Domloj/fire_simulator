import { useEffect, useRef } from 'react';
import maplibre from 'maplibre-gl';
import { useMap } from './MapLibre';
import { agentPositionController, Pos } from '../../features/maps/AgentPositionController';
import { eventEmitter } from '@shared/utils/eventEmitter';
import { reduxStore } from '../../store/reduxStore';

type MarkerEntry = {
  marker: maplibregl.Marker;
  lastPos: Pos; // last reported logical position
  targetPos?: { lng: number; lat: number }; // target position to animate towards
  displayPos?: { lng: number; lat: number };
  lastProj?: { x: number; y: number };
  lastSeen: number;
  lastState?: string | undefined;
  lastStateChangeTime?: number;
};

/* 
 * Simulation constants. Probably should be configurable... 
 */

const STATE_STABLE_MS = 200;
const DEFAULT = '#ff6600';

// Colors aligned with Visualizer Legend (see HELP tab -> "Visualizer Legend")
// Fire Brigade:
//   - Extinguishing: rgb(255, 0, 0)
//   - Travelling:    rgb(0, 100, 255)
//   - Available:     rgb(0, 200, 0)

const FIRE_BRIGADE_COLORS: Record<string, string> = {
  TRAVELLING:    '#0064ff', // niebieski — w drodze
  EXTINGUISHING: '#ff0000', // czerwony — gaszenie
  AVAILABLE:     '#ffffff'  // bialy — wolna (zielony ginal na lesie)
};

// Forester Patrols:
//   - Patrolling:    rgb(255, 165, 0)
//   - Travelling:    rgb(173, 216, 230)
//   - Available/Idle:rgb(128, 128, 128)

const FORESTER_COLORS: Record<string, string> = {
  PATROLLING: '#ffa500', // rgb(255, 165, 0)
  TRAVELLING: '#add8e6', // rgb(173, 216, 230)
  AVAILABLE:  '#808080'  // rgb(128, 128, 128)
};

export default function AgentMarkerManager() {
  const map = useMap();
  const registryRef = useRef<Map<string, MarkerEntry>>(new Map());
  const trailsRef = useRef<Map<string, Array<{ lng: number; lat: number; x?: number; y?: number; t: number }>>>(new Map());
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const needsReprojectRef = useRef<boolean>(false);
  const showTrailsRef = useRef<boolean>(false);

  // const TRAIL_MAX_POINTS = 5000; // max points per agent - increased for full history
  const TRAIL_MIN_PIXEL_DISTANCE = 1; // min px movement to add a point

  // Listen to global "History paths" toggle from STATS tab (LogTabs).
  useEffect(() => {
    const onToggle = (next?: boolean) => {
      const value = typeof next === 'boolean' ? next : !showTrailsRef.current;
      showTrailsRef.current = value;

      // When turning history off, only clear canvas (keep trails stored for when toggle is turned back on)
      if (!value) {
        const canvas = overlayCanvasRef.current;
        if (canvas) {
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
          }
        }
      }
    };

    eventEmitter.addListener('toggleAgentHistory', onToggle);
    return () => {
      eventEmitter.removeListener('toggleAgentHistory', onToggle);
    };
  }, []);

  useEffect(() => {
    if (!map) return;

    // Create a single overlay canvas for drawing trails
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mapContainer = (map as any).getContainer?.() || (map as any).getDiv?.();
    let canvas: HTMLCanvasElement | null = overlayCanvasRef.current;
    
    if (!canvas && mapContainer) {
      canvas = document.createElement('canvas');
      canvas.style.position = 'absolute';
      canvas.style.top = '0';
      canvas.style.left = '0';
      canvas.style.width = '100%';
      canvas.style.height = '100%';
      canvas.style.pointerEvents = 'none';
      canvas.style.zIndex = '100';
      mapContainer.appendChild(canvas);
      overlayCanvasRef.current = canvas;
    }

    // Resize handling for canvas with DPR scaling
    const resizeCanvas = () => {
      if (!canvas || !mapContainer) return;
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, Math.floor(mapContainer.clientWidth));
      const h = Math.max(1, Math.floor(mapContainer.clientHeight));
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      needsReprojectRef.current = true;
    };

    resizeCanvas();
    const ro = new ResizeObserver(resizeCanvas);
    if (mapContainer) ro.observe(mapContainer);
    const onMove = () => { needsReprojectRef.current = true; };
    map.on('move', onMove);

    // Animation loop
    let animRafId: number | null = null;
    let lastAnimTs = performance.now();
    const ANIM_SMOOTH_MS = 360 // 180; // time constant in ms for smoothing towards target

    const animate = (ts?: number) => {
      const nowTsAnim = ts ?? performance.now();
      let dt = nowTsAnim - lastAnimTs;
      if (dt <= 0) dt = 16;
      lastAnimTs = nowTsAnim;
      const alpha = 1 - Math.exp(-dt / ANIM_SMOOTH_MS);

      for (const [key, entry] of registryRef.current.entries()) {
        const target = entry.targetPos ?? entry.lastPos;
        const display = entry.displayPos ?? entry.lastPos;
        
        if (typeof window !== 'undefined' && (window as any).__DEBUG_AGENT_ANIMATION && 
            (Math.abs(target.lng - display.lng) > 0.0001 || Math.abs(target.lat - display.lat) > 0.0001)) {
          // console.log('[AgentMarkerManager] Animating', key, 'from', display, 'to', target);
        }
        
        const newLng = display.lng + (target.lng - display.lng) * alpha;
        const newLat = display.lat + (target.lat - display.lat) * alpha;
        entry.displayPos = { lng: newLng, lat: newLat };

        try {
          entry.marker.setLngLat([newLng, newLat]);
        } catch (e) { /* ignore */ }
      }

      // Draw all trails on overlay canvas (AFTER all agents are processed)
      try {
        const canvas = overlayCanvasRef.current;
        if (canvas) {
          const ctx = canvas.getContext('2d');
          if (ctx) {
            const w = canvas.width;
            const h = canvas.height;

            ctx.clearRect(0, 0, w, h);

            if (!showTrailsRef.current) {
              animRafId = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame(animate) : null;
              return;
            }

            if (needsReprojectRef.current) {
              for (const [, arr] of trailsRef.current.entries()) {
                for (const p of arr) {
                  try {
                    const proj = (map as any).project([p.lng, p.lat]);
                    p.x = proj.x;
                    p.y = proj.y;
                  } catch (err) { /* ignore */ }
                }
              }
              needsReprojectRef.current = false;
            }

            // Draw each trail for all agents
            for (const [key, arr] of trailsRef.current.entries()) {
              if (!arr || arr.length < 2) continue;

              const entryForKey = registryRef.current.get(key);
              const sampleState = entryForKey?.lastState;
              const unitType = key.split(':')[0];
              const colorHex = getColorFor(

                Number(key.split(':')[1]),
                unitType === 'fireBrigade' ? 'fireBrigade' : 'foresterPatrol',
                sampleState
              );

              const r = parseInt(colorHex.slice(1, 3), 16);
              const g = parseInt(colorHex.slice(3, 5), 16);
              const b = parseInt(colorHex.slice(5, 7), 16);

              for (let i = 0; i < arr.length - 1; i++) {
                const p1 = arr[i];
                const p2 = arr[i + 1];

                try {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  if (typeof p1.x !== 'number' || typeof p1.y !== 'number') {
                    const proj1 = (map as any).project([p1.lng, p1.lat]);
                    p1.x = proj1.x; p1.y = proj1.y;
                  }

                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  if (typeof p2.x !== 'number' || typeof p2.y !== 'number') {
                    const proj2 = (map as any).project([p2.lng, p2.lat]);
                    p2.x = proj2.x; p2.y = proj2.y;
                  }
                } catch (e) { /* ignore projection errors */ }


                const ageFactor = i / (arr.length - 1); // 0..1
                const alpha = 0.08 + 0.82 * ageFactor; // 0.08..0.9
                ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
                ctx.lineWidth = 1.5;
                ctx.shadowBlur = 0;
                ctx.shadowColor = 'transparent';
                
                ctx.beginPath();
                ctx.moveTo(p1.x ?? 0, p1.y ?? 0);
                ctx.lineTo(p2.x ?? 0, p2.y ?? 0);
                ctx.stroke();
                
              }
            }
          }
        }
      } catch (e) {
        // ignore canvas errors
      }

      animRafId = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame(animate) : null;
    };

    animRafId = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame(animate) : null;
    // Clean up canvas and move listener on unmount
    const cleanupCanvas = () => {
      try { ro.disconnect(); } catch (e) { /* ignore resize observer errors */ }
      try { map.off('move', onMove); } catch (e) { /* ignore map listener removal errors */ }
      if (typeof animRafId === 'number') {
        try { cancelAnimationFrame(animRafId); } catch (e) { /* ignore */ }
        animRafId = null;
      }
      const canvasEl = overlayCanvasRef.current;
      if (canvasEl && canvasEl.parentNode) {
        try { canvasEl.parentNode.removeChild(canvasEl); } catch (e) { /* ignore DOM removal errors */ }
      }
      overlayCanvasRef.current = null;
    };
    let lastStateLookup: { 
      brigades: Record<number, string>; 
      patrols:  Record<number, string> 
    } = { brigades: {}, patrols: {} };

    const getColorFor = (_id: number, unitType: string | undefined, state: string | undefined) => {
      if (unitType === 'fireBrigade'){
        return FIRE_BRIGADE_COLORS[state ?? 'AVAILABLE'] ?? DEFAULT;
      }
      
      if (unitType === 'foresterPatrol'){
        return FORESTER_COLORS[state ?? 'AVAILABLE'] ?? DEFAULT;
      }
      return DEFAULT;
    };

    const unsub = agentPositionController.subscribe((positions) => {
      const now = Date.now();

      // DEBUG: log incoming positions to ensure agent updates arrive
      try {
        if (typeof window !== 'undefined' && (window as any).__DEBUG_AGENT_POSITIONS) {
          try {
            // console.debug('[AgentMarkerManager] incoming positions', { size: positions.size, keys: Array.from(positions.keys()).slice(0,10), sample: Array.from(positions.entries()).slice(0,5) });
          } catch (e) { /* ignore debug errors */ }
        }
        // Always log first few updates to debug movement issues (throttled)
        if (positions.size > 0 && (!(window as any).__lastPosLog || Date.now() - (window as any).__lastPosLog > 2000)) {
          const sample = Array.from(positions.entries()).slice(0, 3);
          // console.log('[AgentMarkerManager] Received positions:', positions.size, 'agents. Sample:', sample.map(([k, p]) => ({ key: k, id: p.id, lng: p.lng, lat: p.lat, state: p.state })));
          (window as any).__lastPosLog = Date.now();
        }
      } catch (e) { /* ignore */ }

      try {
        const state = reduxStore.getState();
        const brigades = (state.mapConfiguration.configuration?.fireBrigades || []).reduce((acc: Record<number, string>, fb: { fireBrigadeId: number; state: string }) => { acc[fb.fireBrigadeId] = fb.state; return acc; }, {} as Record<number, string>);
        const patrols = (state.mapConfiguration.configuration?.foresterPatrols || []).reduce((acc: Record<number, string>, fp: { foresterPatrolId: number; state: string }) => { acc[fp.foresterPatrolId] = fp.state; return acc; }, {} as Record<number, string>);
        lastStateLookup = { brigades, patrols };
      } catch (e) {
        // pass 
      }

      for (const [key, pos] of positions) {
        if (!Number.isFinite(pos.lng) || !Number.isFinite(pos.lat)) { continue; }
        if (Math.abs(pos.lng) < 1e-6 && Math.abs(pos.lat) < 1e-6) { continue; }

        const keyStr = String(key);
        const entry = registryRef.current.get(keyStr);
        const unitType = pos.unitType ?? undefined;
        const idNum = pos.id ?? parseInt(keyStr.split(':')[1], 10);
        const stateVal = pos.state ?? (unitType === 'fireBrigade' ? lastStateLookup.brigades[idNum] : lastStateLookup.patrols[idNum]);

        if (!entry) {
          const container = document.createElement('div');

          container.className = 'agent-marker-container';
          // Positioning: use absolute-positioned children so the marker's center remains at the geo coord
          container.style.position = 'relative';
          container.style.pointerEvents = 'auto';
          container.style.cursor = 'pointer';
          container.style.zIndex = '150';

          container.onclick = (e) => {
            e.stopPropagation();
            if (unitType === 'fireBrigade') {
              eventEmitter.emit('onFireBrigadeClick', { fireBrigadeId: idNum, state: stateVal });
            }
          };

          // compute marker size first so label can be positioned relative to it (match ScatterplotLayer radii -> diameter)
          const sectorCountForMarker = (reduxStore.getState().mapConfiguration.configuration?.sectors?.length) || 0;
          const markerDiameterPx = sectorCountForMarker > 400 ? 5 : sectorCountForMarker > 100 ? 7 : sectorCountForMarker > 25 ? 9 : 10;

          const label = document.createElement('div');
          label.className = 'agent-label';
          const sectorCountForLabel = sectorCountForMarker;
          // Match TextLayer sizing: more sectors -> smaller labels
          const fontSizePx = sectorCountForLabel > 100 ? 5 : sectorCountForLabel > 50 ? 6 : sectorCountForLabel > 25 ? 7 : 7;
          const prefix = unitType === 'foresterPatrol' ? 'ForesterPatrol' : 'FireBrigade';
          label.innerText = `${prefix}_${String(idNum).padStart(2, '0')}`;

          label.style.display = 'inline-block';
          label.style.color = 'white';
          label.style.fontSize = `${fontSizePx}px`;
          label.style.fontWeight = 'bold';
          label.style.textShadow = '0px 0px 2px black';
          label.style.whiteSpace = 'nowrap';
          label.style.fontFamily = 'Monaco, monospace';
          // Slightly translucent black background for better blending
          label.style.backgroundColor = 'rgba(0,0,0,0.72)';
          label.style.opacity = '0.95';
          label.style.padding = '1px 4px';
          label.style.borderRadius = '3px';
          label.style.pointerEvents = 'auto';
          // position label absolutely above the marker so the marker center is the true geo center
          label.style.position = 'absolute';
          label.style.left = '50%';
          // Use fixed pixel offset to match deck.gl TextLayer offset (pixel offset -15)
          label.style.transform = 'translate(-50%, -15px)';
          label.style.boxSizing = 'border-box';
          label.style.width = 'auto';
          container.appendChild(label);

          const el = document.createElement('div');
          el.className = 'agent-marker';

          // reuse previously computed markerDiameterPx

          // Brygada = ostry kwadrat, wyraźnie większy; patrol = kółko. Kształt
          // i rozmiar od razu odróżniają typ jednostki, nawet przy małych
          // ikonach (2px zaokrąglenia na 9px markerze robilo z kwadratu kółko).
          const isBrigade = unitType === 'fireBrigade';
          const markerSizePx = isBrigade ? markerDiameterPx + 4 : markerDiameterPx;
          el.style.width = `${markerSizePx}px`;
          el.style.height = `${markerSizePx}px`;
          el.style.borderRadius = isBrigade ? '0' : '50%';
          // Brygada ma ciemną obwódkę, żeby biały (wolny) kwadrat miał kontur;
          // patrol zostaje przy białej.
          el.style.border = isBrigade ? '2px solid #1a1a1a' : '2px solid white';

          el.style.position = 'absolute';
          el.style.left = '50%';
          el.style.top = '50%';
          el.style.transform = 'translate(-50%, -50%)';

          const color = getColorFor(idNum, unitType, stateVal);
          el.style.boxShadow = stateVal === 'EXTINGUISHING' ? '0 0 8px rgba(255,0,0,0.95)' : '0 0 4px rgba(0,0,0,0.5)';
          el.style.background = color;
          el.style.transition = 'transform 0.08s linear, width 0.2s linear, height 0.2s linear, box-shadow 0.2s linear, background 0.15s linear';

          container.appendChild(el);

          const marker = new maplibre.Marker({ element: container, anchor: 'center' })
            .setLngLat([pos.lng, pos.lat])
            .addTo(map as maplibregl.Map);

          // Initialize trail with first position point (history starts from beginning)
          try {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const proj = (map as any).project([pos.lng, pos.lat]);
            const trails = trailsRef.current.get(keyStr) || [];
            trails.push({ lng: pos.lng, lat: pos.lat, x: proj.x, y: proj.y, t: now });
            // if (trails.length > TRAIL_MAX_POINTS) trails.shift();
            trailsRef.current.set(keyStr, trails);
          } catch (e) { /* ignore projection errors */ }
          
          registryRef.current.set(keyStr, { 
            marker, 
            lastPos: pos, 
            displayPos: { lng: pos.lng, lat: pos.lat }, 
            targetPos: { lng: pos.lng, lat: pos.lat }, 
            lastSeen: now, 
            lastState: stateVal, 
            lastStateChangeTime: now,
            lastProj: undefined // Will be set on first animation frame
          });


        } else {
          const nowTs = Date.now();

          try {
            const container = entry.marker.getElement();
            const el = container.lastElementChild as HTMLElement;

            try {
              const labelEl = container.firstElementChild as HTMLElement;
              if (labelEl) {
                const sectorCountForLabel = (reduxStore.getState().mapConfiguration.configuration?.sectors?.length) || 0;
                  // Match TextLayer sizing: more sectors -> smaller labels
                  const fontSizePx = sectorCountForLabel > 100 ? 6 : sectorCountForLabel > 50 ? 7 : sectorCountForLabel > 25 ? 8 : 8;
                  const prefix = unitType === 'foresterPatrol' ? 'FP' : 'FB';
                  labelEl.innerText = `${prefix}_${String(idNum).padStart(2, '0')}`;
                  labelEl.style.fontSize = `${fontSizePx}px`;
                  labelEl.style.color = 'white';
                  labelEl.style.fontWeight = 'bold';
                  labelEl.style.textShadow = '0px 0px 2px black';
                  labelEl.style.whiteSpace = 'nowrap';
                  labelEl.style.fontFamily = 'Monaco, monospace';
                  // Slightly translucent black background for better blending
                  labelEl.style.backgroundColor = 'rgba(0,0,0,0.72)';
                  labelEl.style.opacity = '0.95';
                  labelEl.style.padding = '1px 4px';
                  labelEl.style.borderRadius = '3px';
                  labelEl.style.pointerEvents = 'auto';
                  // keep label positioned above marker center (match TextLayer offset)
                  labelEl.style.transform = 'translate(-50%, -15px)';
              }
            } catch (e) {
              /* ignore DOM errors */
            }

            const desiredColor = getColorFor(idNum, unitType, stateVal);
            const desiredBoxShadow = stateVal === 'EXTINGUISHING' ? '0 0 8px rgba(255,0,0,0.95)' : '0 0 4px rgba(0,0,0,0.45)';

            if (entry.lastState !== stateVal) {
              if (!entry.lastStateChangeTime) entry.lastStateChangeTime = nowTs;
              if (nowTs - (entry.lastStateChangeTime || 0) >= STATE_STABLE_MS) {
                if (el && el.style.background !== desiredColor) {
                  el.style.background = desiredColor;
                }
                entry.lastState = stateVal;
                entry.lastStateChangeTime = nowTs;
              }
            } else {
              if (el && el.style.background !== desiredColor) el.style.background = desiredColor;
            }

            try {
              const sectorCountForMarkerUpdate = (reduxStore.getState().mapConfiguration.configuration?.sectors?.length) || 0;
                const desiredDiameter = sectorCountForMarkerUpdate > 400 ? 5 : sectorCountForMarkerUpdate > 100 ? 7 : sectorCountForMarkerUpdate > 25 ? 9 : 10;
              if (el) {
                if (el.style.width !== `${desiredDiameter}px` || el.style.height !== `${desiredDiameter}px`) {
                  el.style.width = `${desiredDiameter}px`;
                  el.style.height = `${desiredDiameter}px`;
                }
                if (el.style.boxShadow !== desiredBoxShadow) {
                  el.style.boxShadow = desiredBoxShadow;
                }
              }
            } catch (e) {
              /* ignore DOM errors */
            }


          } catch (e) {
            // ignore DOM errors
          }

          try {
            // Do not setLngLat directly here; set a target position and let animation RAF loop move the marker smoothly.
            const prevDisplay = entry.displayPos || { lng: entry.lastPos.lng, lat: entry.lastPos.lat };
            const dist = Math.hypot(pos.lng - prevDisplay.lng, pos.lat - prevDisplay.lat);
            // If a very large jump occurred, snap the displayed position immediately to avoid long interpolation
            if (dist > 0.05) {
              entry.displayPos = { lng: pos.lng, lat: pos.lat };
              try { entry.marker.setLngLat([pos.lng, pos.lat]); } catch (e) { /* ignore */ }
              // update last projected point so trail doesn't leave a huge span
              try {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const proj = (map as any).project([pos.lng, pos.lat]);
                entry.lastProj = { x: proj.x, y: proj.y };
                // Record trail point for large jumps (ALWAYS record, toggle only controls drawing)
                const trails = trailsRef.current.get(keyStr) || [];
                trails.push({ lng: pos.lng, lat: pos.lat, x: proj.x, y: proj.y, t: now });
                // if (trails.length > TRAIL_MAX_POINTS) trails.shift();
                trailsRef.current.set(keyStr, trails);
              } catch (e) { /* ignore */ }
            }
            
            // Record trail point when position updates (ALWAYS record, toggle only controls drawing)
            // This ensures trails are recorded from the beginning of simulation, not just when toggle is on
            try {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const proj = (map as any).project([pos.lng, pos.lat]);
              const px = proj.x;
              const py = proj.y;
              const lastP = entry.lastProj;

              // Only record if moved enough pixels to avoid too many points
              if (!lastP || Math.hypot(px - lastP.x, py - lastP.y) >= TRAIL_MIN_PIXEL_DISTANCE) {
                const trails = trailsRef.current.get(keyStr) || [];
                trails.push({ lng: pos.lng, lat: pos.lat, x: px, y: py, t: now });
                // if (trails.length > TRAIL_MAX_POINTS) trails.shift();
                trailsRef.current.set(keyStr, trails);
                entry.lastProj = { x: px, y: py };
              }

            } catch (e) { /* ignore projection errors */ }
          } catch (e) {
            // ignore map errors
          }

          entry.targetPos = { lng: pos.lng, lat: pos.lat };
          entry.lastPos = pos;
          entry.lastSeen = now;
        }
      }

      // Prune stale markers immediately if they are missing from positions
      const STALE_THRESHOLD = 30_000; // 30s
      for (const [key, entry] of registryRef.current.entries()) {
        if (!positions.has(key)) {
          if (now - entry.lastSeen > STALE_THRESHOLD) {
            try {
              entry.marker.remove();
            } catch (e) {
              // pass
            }
            registryRef.current.delete(key);
          }
        }
      }


      for (const [tkey, arr] of trailsRef.current.entries()) {
        if (!arr || arr.length === 0) {
          trailsRef.current.delete(tkey);
        }
      }
    });

    const registry = registryRef.current;
    const trails = trailsRef.current;

    return () => {
      unsub();
      // cleanup markers
      for (const entry of registry.values()) {
        try { entry.marker.remove(); } catch (e) { /* ignore */ }
      }
      registry.clear();
      cleanupCanvas();
    };
  }, [map]);

  return null; 
}
