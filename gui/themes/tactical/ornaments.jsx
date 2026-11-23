// Tactical's drawn kit: every ornament on its pages is one of these, in inline SVG, 1 px strokes in
// currentColor (a parent's colour token) so they stay crisp at 1× and follow the theme. They take
// data (value, label, samples) and draw it; the motion is tactical.css's (.tx-*): lines draw on with
// stroke-dashoffset, marks snap with transform, nothing else animates.
'use strict';

const clamp01 = v => Math.max(0, Math.min(1, Number(v) || 0));

// Crop marks on a block's four corners. Put it inside a position:relative block; `inset` pulls the
// marks out past the block's edge. Hovering the block (.tx-bracketed:hover) closes them in.
export function Brackets({ size = 10, inset = -4 }) {
  const d = `M0 ${size}V0H${size}`;
  return ['tl', 'tr', 'br', 'bl'].map((c, i) => (
    <svg key={c} className={'tx-bk tx-bk-' + c} width={size} height={size} viewBox={`0 0 ${size} ${size}`}
      style={{ '--bk-inset': inset + 'px', '--i': i }} aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" transform={`rotate(${i * 90} ${size / 2} ${size / 2})`} />
    </svg>
  ));
}

// A + registration mark
export function Reg({ size = 9, className = '' }) {
  const h = size / 2;
  return (
    <svg className={'tx-reg ' + className} width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <path d={`M${h} 0V${size}M0 ${h}H${size}`} stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

// Node markers: diamond (a step), triangle (a pointer), dot (a point in a ring)
export function Node({ kind = 'diamond', size = 8, filled = false, className = '' }) {
  const s = size, h = s / 2;
  const shape = kind === 'triangle' ? <path d={`M0 0L${s} ${h}L0 ${s}Z`} />
    : kind === 'dot' ? <><circle cx={h} cy={h} r={h - 0.75} /><circle cx={h} cy={h} r={1.2} fill="currentColor" /></>
      : <path d={`M${h} 0.75L${s - 0.75} ${h}L${h} ${s - 0.75}L0.75 ${h}Z`} />;
  return (
    <svg className={'tx-node ' + className} width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden="true"
      fill={filled && kind !== 'dot' ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1">
      {shape}
    </svg>
  );
}

// A solid label block: a big numeral (or word) and a caption under it ("01" / "BAY")
export function LabelBlock({ value, caption, className = '', title }) {
  return (
    <div className={'tx-lb ' + className} title={title}>
      <span className="tx-lb-val" key={String(value)}>{value}</span>
      {caption && <span className="tx-lb-cap">{caption}</span>}
    </div>
  );
}

// A diagonal hatched band behind a warning word
export function Hatch({ children, className = '' }) {
  return (
    <span className={'tx-hatch ' + className}>
      <svg aria-hidden="true" preserveAspectRatio="none"><defs>
        <pattern id="tx-hatch-p" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="currentColor" strokeWidth="2" />
        </pattern>
      </defs><rect width="100%" height="100%" fill="url(#tx-hatch-p)" /></svg>
      <b>{children}</b>
    </span>
  );
}

// A tick scale with labelled stops and a marker on the chosen one. `stops` [{key, label}], `value` a key,
// `onPick(key)` makes each stop a button. `minor` ticks fall between stops.
export function Ruler({ stops, value, onPick, minor = 4, disabled = false, className = '', label }) {
  const n = stops.length;
  const at = Math.max(0, stops.findIndex(s => s.key === value));
  const pos = i => (n === 1 ? 50 : (i / (n - 1)) * 100);
  const ticks = [];
  for (let i = 0; i < n - 1; i++) {
    for (let j = 1; j <= minor; j++) ticks.push(pos(i) + (pos(i + 1) - pos(i)) * (j / (minor + 1)));
  }
  return (
    <div className={'tx-ruler' + (disabled ? ' off' : '') + ' ' + className} role="radiogroup" aria-label={label}>
      <svg className="tx-ruler-svg" aria-hidden="true">
        <line className="tx-draw" x1="0" y1="11.5" x2="100%" y2="11.5" stroke="currentColor" strokeWidth="1" pathLength="1" />
        {ticks.map((x, i) => <line key={i} x1={x + '%'} x2={x + '%'} y1="8" y2="11.5" stroke="currentColor" strokeWidth="1" opacity="0.55" />)}
        {stops.map((s, i) => <line key={s.key} x1={pos(i) + '%'} x2={pos(i) + '%'} y1="3" y2="11.5" stroke="currentColor" strokeWidth="1" />)}
      </svg>
      {/* A full-width layer moved by the stop's share of its own width: the marker slides by transform */}
      <span className="tx-ruler-mark" style={{ transform: `translateX(${pos(at)}%)` }} aria-hidden="true">
        <Node kind="triangle" size={8} filled />
      </span>
      {stops.map((s, i) => (
        <button key={s.key} type="button" role="radio" aria-checked={s.key === value} disabled={disabled}
          className={'tx-ruler-stop' + (s.key === value ? ' on' : '')} style={{ left: pos(i) + '%' }}
          onClick={() => onPick && onPick(s.key)}>{s.label}</button>
      ))}
    </div>
  );
}

// A ring instrument: degree ticks round a 270° dial, the value as an arc with a chevron at its head,
// labelled stops at 0/25/50/75/100. `live` draws the arc in the accent; children sit in the middle.
export function RingGauge({ value = 0, size = 240, live = false, warn = false, children, className = '' }) {
  const c = size / 2, r = c - 22, ri = r - 9;
  const START = 135, SWEEP = 270;
  const pt = (deg, rad) => {
    const a = (deg * Math.PI) / 180;
    return [c + rad * Math.cos(a), c + rad * Math.sin(a)];
  };
  const arc = (rad, from, to) => {
    const [x1, y1] = pt(from, rad), [x2, y2] = pt(to, rad);
    return `M${x1} ${y1}A${rad} ${rad} 0 ${to - from > 180 ? 1 : 0} 1 ${x2} ${y2}`;
  };
  const v = clamp01(value);
  const ticks = [];
  for (let i = 0; i <= 50; i++) {
    const deg = START + (SWEEP * i) / 50;
    const major = i % 5 === 0;
    const [x1, y1] = pt(deg, r + (major ? 8 : 4)), [x2, y2] = pt(deg, r + 1);
    ticks.push(<line key={i} x1={x1} y1={y1} x2={x2} y2={y2} className={major ? 'maj' : ''} style={{ '--i': i }} />);
  }
  const labels = [0, 25, 50, 75, 100].map(p => {
    const [x, y] = pt(START + (SWEEP * p) / 100, r + 17);
    return <text key={p} x={x} y={y + 3} textAnchor="middle">{p}</text>;
  });
  const head = START + SWEEP * v;
  return (
    <div className={'tx-ring' + (live ? ' live' : '') + (warn ? ' warn' : '') + ' ' + className} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <g className="tx-ring-ticks">{ticks}</g>
        <g className="tx-ring-labels">{labels}</g>
        <path className="tx-ring-track tx-draw" d={arc(ri, START, START + SWEEP)} pathLength="1" />
        <path className="tx-ring-band" d={arc(ri - 5, START, START + SWEEP)} />
        <path className="tx-ring-val" d={arc(ri, START, START + SWEEP)} pathLength="1"
          style={{ strokeDashoffset: 1 - v }} />
        <g className="tx-ring-head" style={{ transform: `rotate(${head - START}deg)`, transformOrigin: `${c}px ${c}px` }}>
          <path d={(() => { const [ax, ay] = pt(START, ri - 13), [bx, by] = pt(START - 3.2, ri - 7), [cx, cy] = pt(START + 3.2, ri - 7); return `M${ax} ${ay}L${bx} ${by}M${ax} ${ay}L${cx} ${cy}`; })()} />
        </g>
        <circle className="tx-ring-hub" cx={c} cy={c} r={ri - 22} />
      </svg>
      <div className="tx-ring-mid">{children}</div>
    </div>
  );
}

// A segmented bar: `value` 0–1 lights that share of `segments`
export function SegBar({ value = 0, segments = 20, className = '', title }) {
  const lit = Math.round(clamp01(value) * segments);
  return (
    <span className={'tx-seg ' + className} title={title} aria-hidden={title ? undefined : 'true'}>
      {Array.from({ length: segments }, (_, i) => <i key={i} className={i < lit ? 'on' : ''} />)}
    </span>
  );
}

// A sparkline in a framed box with a baseline scale; the newest sample on the right
export function Spark({ samples = [], width = 300, height = 40, className = '', label }) {
  const pts = samples.length ? samples : [0];
  const max = Math.max(...pts, 1);
  const step = pts.length > 1 ? width / (pts.length - 1) : width;
  const line = pts.map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - (v / max) * (height - 6)).toFixed(1)}`).join(' ');
  return (
    <div className={'tx-spark ' + className}>
      <svg className="tx-spark-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        {[0.25, 0.5, 0.75].map(f => <line key={f} className="tx-spark-grid" x1={width * f} x2={width * f} y1="0" y2={height} />)}
        <polyline className="tx-spark-line" points={line} vectorEffect="non-scaling-stroke" />
      </svg>
      {label && <span className="tx-spark-cap">{label}</span>}
      <Brackets size={6} inset={-1} />
    </div>
  );
}

// A section caption: index number, a rule that draws on, the title and its Japanese subtitle
export function Caption({ num, title, jp, children, className = '' }) {
  return (
    <div className={'tx-cap ' + className}>
      {num && <span className="tx-cap-num">{num}</span>}
      <span className="tx-cap-title">{title}</span>
      {jp && <span className="tx-cap-jp">{jp}</span>}
      <svg className="tx-cap-rule" aria-hidden="true" preserveAspectRatio="none">
        <line className="tx-draw" x1="0" y1="0.5" x2="100%" y2="0.5" pathLength="1" />
      </svg>
      {children}
    </div>
  );
}

// A light band that sweeps across its block while something is live (pure transform)
export function ScanLine({ active = true }) {
  return active ? <span className="tx-scan" aria-hidden="true" /> : null;
}
