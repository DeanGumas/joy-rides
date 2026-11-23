import { h, render } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import htm from 'htm';
import { createMap, DIFFICULTY } from './map.js';

const html = htm.bind(h);
const params = new URLSearchParams(location.search); // e.g. ?season=winter&slope=1
const FT = 3.28084;
const DIFF_ORDER = ['green', 'blue', 'black', 'double-black', 'freeride', 'unknown'];

const fmtLen = (m, units) => (m == null ? '–' : units === 'ft'
  ? (m * FT >= 5280 ? `${(m * FT / 5280).toFixed(2)} mi` : `${Math.round(m * FT).toLocaleString()} ft`)
  : (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`));
const cap = (s) => s && s.charAt(0).toUpperCase() + s.slice(1).replaceAll('_', ' ');
const fmtElev = (m, units) => (m == null ? '–' : units === 'ft' ? `${Math.round(m * FT).toLocaleString()} ft` : `${Math.round(m).toLocaleString()} m`);

async function fetchJSON(url) {
  const r = await fetch(url);
  return r.ok ? r.json() : null;
}

const SYMBOL = { green: '●', blue: '■', black: '◆', 'double-black': '◆◆', freeride: '▲', unknown: '○' };

function DifficultyIcon({ difficulty }) {
  const d = DIFFICULTY[difficulty] ?? DIFFICULTY.unknown;
  return html`<span class="sym" style=${{ '--c': d.color }}>${SYMBOL[difficulty] ?? '○'}</span>`;
}

function DifficultyBadge({ difficulty }) {
  const d = DIFFICULTY[difficulty] ?? DIFFICULTY.unknown;
  return html`<span class="badge"><${DifficultyIcon} difficulty=${difficulty} />${d.label}</span>`;
}

function Toggle({ label, checked, onChange, children }) {
  return html`
    <label class="toggle">
      <input type="checkbox" checked=${checked} onChange=${(e) => onChange(e.currentTarget.checked)} />
      <span>${label}</span>${children}
    </label>`;
}

function SlopeLegend({ classes }) {
  return html`
    <div class="legend">
      ${classes.map((c) => html`
        <div class="legend-row"><span class="swatch" style=${{ background: c.color }}></span>
        ${c.max >= 90 ? `${c.min}°+` : `${c.min}–${c.max}°`}</div>`)}
      <p class="hint">Most avalanches start on 30–45° slopes. Slope shading is no substitute for a forecast.</p>
    </div>`;
}

function InfoCard({ feature, units, onClose }) {
  if (!feature) return null;
  const isLift = feature.kind === 'lift';
  const rows = isLift
    ? [['Type', cap(feature.lift_type)], ['Length', fmtLen(feature.length_m, units)],
       ['Vertical rise', fmtLen(feature.vertical_m, units)], ['Top', fmtElev(feature.top_m, units)],
       ['Bottom', fmtElev(feature.bottom_m, units)], ['Seats', feature.occupancy], ['Ride time', feature.duration_min && `${feature.duration_min} min`]]
    : [['Length', fmtLen(feature.length_m, units)], ['Vertical drop', fmtLen(feature.vertical_m, units)],
       ['Top', fmtElev(feature.top_m, units)], ['Bottom', fmtElev(feature.bottom_m, units)],
       ['Avg pitch', feature.avg_pitch_deg != null && `${feature.avg_pitch_deg}°`],
       ['Steepest 30 m', feature.max_pitch_deg != null && `${feature.max_pitch_deg}°`],
       ['Grooming', cap(feature.grooming)], ['Gladed', feature.gladed ? 'Yes' : null]];
  return html`
    <div class="card info">
      <button class="close" onClick=${onClose} aria-label="Close">×</button>
      <div class="eyebrow">${isLift ? 'Lift' : 'Run'}</div>
      <h2>${feature.name ?? 'Unnamed'}</h2>
      ${!isLift && html`<${DifficultyBadge} difficulty=${feature.difficulty} />`}
      <dl>${rows.filter(([, v]) => v).map(([k, v]) => html`<dt>${k}</dt><dd>${v}</dd>`)}</dl>
      <a class="osm" href=${`https://www.openstreetmap.org/${feature.id}`} target="_blank" rel="noopener">View / edit on OpenStreetMap ↗</a>
    </div>`;
}

function RunList({ runs, units, selectedId, onPick }) {
  const [q, setQ] = useState('');
  const [diff, setDiff] = useState(null);
  const list = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return runs
      .filter((f) => f.properties.name)
      .filter((f) => !ql || f.properties.name.toLowerCase().includes(ql))
      .filter((f) => !diff || f.properties.difficulty === diff)
      .sort((a, b) => a.properties.name.localeCompare(b.properties.name));
  }, [runs, q, diff]);
  const present = DIFF_ORDER.filter((d) => runs.some((f) => f.properties.difficulty === d));
  return html`
    <div class="runlist">
      <input class="search" type="search" placeholder="Search ${runs.length} runs…" value=${q} onInput=${(e) => setQ(e.currentTarget.value)} />
      <div class="chips">
        ${present.map((d) => html`
          <button class=${`chip ${diff === d ? 'on' : ''}`} onClick=${() => setDiff(diff === d ? null : d)}>
            <${DifficultyIcon} difficulty=${d} />${DIFFICULTY[d].label}</button>`)}
      </div>
      <ul>
        ${list.map((f) => html`
          <li class=${f.properties.id === selectedId ? 'sel' : ''} onClick=${() => onPick(f)}>
            <${DifficultyIcon} difficulty=${f.properties.difficulty} />
            <span class="name">${f.properties.name}</span>
            <span class="meta">${fmtLen(f.properties.vertical_m, units)}</span>
          </li>`)}
      </ul>
    </div>`;
}

function App() {
  const [ctl, setCtl] = useState(null);
  const [meta, setMeta] = useState(undefined);
  const [runs, setRuns] = useState([]);
  const [season, setSeason] = useState(params.get('season') === 'winter' ? 'winter' : 'summer');
  const [groups, setGroups] = useState({ runs: true, lifts: true, labels: true, slope: params.get('slope') === '1', hillshade: true });
  const [exaggeration, setExaggeration] = useState(1);
  const [units, setUnits] = useState('ft');
  const [selected, setSelected] = useState(null);
  const [cursor, setCursor] = useState(null);
  const [panelOpen, setPanelOpen] = useState(true);

  useEffect(() => {
    fetchJSON('/tiles/meta.json').then((m) => setMeta(m));
    fetchJSON('/geo/runs.geojson').then((g) => setRuns(g?.features ?? []));
  }, []);

  useEffect(() => {
    if (meta === undefined || ctl) return;
    const created = createMap(document.getElementById('map'), meta, {
      onSelect: setSelected,
      onHover: async (ll) => setCursor(await fetchJSON(`/api/point?lon=${ll.lng}&lat=${ll.lat}`)),
    });
    setCtl(created);
    window.joy = created; // handy for poking at the map from devtools
  }, [meta]);

  const whenReady = (fn) => { ctl?.ready.then(fn); };
  useEffect(() => whenReady(() => ctl.setSeason(season)), [ctl, season]);
  useEffect(() => whenReady(() => Object.entries(groups).forEach(([g, v]) => ctl.setGroup(g, v))), [ctl, groups]);
  useEffect(() => whenReady(() => ctl.setExaggeration(exaggeration)), [ctl, exaggeration]);
  useEffect(() => whenReady(() => ctl.highlight(selected?.kind === 'run' ? selected.id : null)), [ctl, selected]);

  const pick = (f) => {
    setSelected({ ...f.properties, kind: 'run' });
    ctl?.flyToFeature(f);
  };
  const setGroup = (g) => (v) => setGroups({ ...groups, [g]: v });

  return html`
    <aside class=${`panel ${panelOpen ? '' : 'collapsed'}`}>
      <header>
        <div>
          <h1>Joy Rides</h1>
          <div class="sub">${meta?.name ?? 'Mammoth'} · 1 m lidar terrain</div>
        </div>
        <button class="collapse" onClick=${() => setPanelOpen(!panelOpen)} aria-label="Toggle panel">${panelOpen ? '‹' : '›'}</button>
      </header>
      <div class="body">
        ${meta === null && html`<div class="warn">No rendered tiles yet. Run <code>python -m pipeline.build_tiles</code> for NAIP imagery and slope shading.</div>`}
        <section>
          <h3>Imagery</h3>
          <div class="seg">
            ${['summer', 'winter'].map((s) => html`
              <button class=${season === s ? 'on' : ''} disabled=${!meta} onClick=${() => setSeason(s)}>${s === 'summer' ? 'Summer' : 'Winter (simulated)'}</button>`)}
          </div>
        </section>
        <section>
          <h3>Layers</h3>
          <${Toggle} label="Runs" checked=${groups.runs} onChange=${setGroup('runs')} />
          <${Toggle} label="Lifts" checked=${groups.lifts} onChange=${setGroup('lifts')} />
          <${Toggle} label="Labels" checked=${groups.labels} onChange=${setGroup('labels')} />
          <${Toggle} label="Hillshade" checked=${groups.hillshade} onChange=${setGroup('hillshade')} />
          <${Toggle} label="Slope angle" checked=${groups.slope} onChange=${setGroup('slope')} />
          ${groups.slope && meta && html`<${SlopeLegend} classes=${meta.slopeClasses} />`}
          <label class="slider">
            <span>Terrain exaggeration <b>${exaggeration.toFixed(1)}×</b></span>
            <input type="range" min="1" max="2" step="0.1" value=${exaggeration} onInput=${(e) => setExaggeration(+e.currentTarget.value)} />
          </label>
          <div class="seg small">
            ${['ft', 'm'].map((u) => html`<button class=${units === u ? 'on' : ''} onClick=${() => setUnits(u)}>${u === 'ft' ? 'Feet' : 'Meters'}</button>`)}
          </div>
        </section>
        <section class="grow">
          <h3>Runs</h3>
          <${RunList} runs=${runs} units=${units} selectedId=${selected?.id} onPick=${pick} />
        </section>
      </div>
    </aside>
    <${InfoCard} feature=${selected} units=${units} onClose=${() => setSelected(null)} />
    ${cursor && html`
      <div class="readout">
        <span>${fmtElev(cursor.elevation_m, units)}</span>
        <span>${cursor.slope_deg}° slope</span>
        <span>${cursor.aspect} aspect</span>
      </div>`}
  `;
}

render(html`<${App} />`, document.getElementById('app'));
