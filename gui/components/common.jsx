// Small shared components: toggles, mascot renderer, modals, toasts, charts.
'use strict';

import { Ico } from './icons.jsx';

export function Toggle({ checked, onChange }) {
  return (
    <div
      className={'toggle' + (checked ? ' on' : '')}
      onClick={() => onChange(!checked)}
    />
  );
}

export function Mascot({ src, className, style, wrapClass }) {
  if (src && typeof src === 'string') {
    const t = src.trimStart();
    if (t.startsWith('<svg') || t.startsWith('<?xml')) {
      const svgHtml = t.startsWith('<?xml') ? src.replace(/^<\?xml[^?]*\?>\s*/i, '') : src;
      return (
        <div
          className={'mascot-wrap ' + (wrapClass || className || '')}
          style={style}
          dangerouslySetInnerHTML={{ __html: svgHtml }}
        />
      );
    }
  }
  return <img src={src} className={className || 'mascot-img'} style={style} alt="" />;
}

export function EditableStat({ value, colorClass, format, onSave }) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState('');
  const inputRef = React.useRef(null);

  const startEdit = () => {
    setDraft(String(value));
    setEditing(true);
  };

  React.useEffect(() => {
    if (editing && inputRef.current) inputRef.current.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    if (onSave && draft !== String(value)) onSave(draft);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="stat-value-input"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false); }}
      />
    );
  }

  return (
    <div
      className={'stat-value editable ' + (colorClass || '')}
      onClick={startEdit}
      title="Click to edit"
    >
      {format ? format(value) : value}
    </div>
  );
}

export function Modal({ title, onClose, children, footer }) {
  React.useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-box">
        <div className="modal-hud" /><div className="modal-hud-br" />
        <div className="modal-header">
          <div className="modal-title">{title}</div>
          <div className="modal-close" onClick={onClose}><Ico name="x" size={14} /></div>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

export function Notif({ notif, dismiss }) {
  if (!notif) return null;
  return (
    <div className={'notif ' + (notif.type || '')} onClick={dismiss} style={{ cursor: 'pointer' }}>
      <div className="notif-title">{notif.title}</div>
      <div className="notif-body">{notif.body}</div>
      {notif.actions && notif.actions.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
          {notif.actions.map(a => (
            <button
              key={a.label}
              className={'btn btn-sm ' + (a.primary ? 'btn-primary' : 'btn-secondary')}
              onClick={e => { e.stopPropagation(); a.onClick(); dismiss(); }}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Pipeline({ stage }) {
  const stages = ['FETCH', 'META', 'DOWNLOAD', 'MERGE', 'INDEX', 'WRITE DB'];
  const idx = { starting: 0, processing: 3, indexing: 4, done: 5 }[stage] ?? 2;

  const items = [];
  stages.forEach((label, i) => {
    const isDone = i < idx;
    const isActive = i === idx;
    items.push(<div key={'d' + i} className={'pl-dot' + (isDone ? ' done' : isActive ? ' active' : '')} />);
    if (i < stages.length - 1) {
      items.push(<div key={'l' + i} className={'pl-line' + (isDone ? ' done' : '')} />);
    }
    items.push(<span key={'lb' + i} className={'pl-label' + (isDone ? ' done' : isActive ? ' active' : '')}>{label}</span>);
    if (i < stages.length - 1) {
      items.push(<div key={'l2' + i} className={'pl-line' + (isDone ? ' done' : '')} />);
    }
  });

  return <div className="pipeline">{items}</div>;
}

export function LineChart({ data, color = 'rgba(0,216,255,0.85)', height = 120, yFormat }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const w = c.offsetWidth;
    if (!w) return;
    c.width = w; c.height = height;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, w, height);
    if (!data || !data.length) return;
    const pts = data.map(d => d.y);
    const labels = data.map(d => d.x);
    const maxV = Math.max(...pts, 1);
    const pad = { l: 44, r: 8, t: 8, b: 20 };
    const cw = w - pad.l - pad.r, ch = height - pad.t - pad.b;
    const fmt = yFormat || (v => String(Math.round(v)));
    [0, 0.5, 1].forEach(f => {
      const y = pad.t + ch * (1 - f);
      ctx.strokeStyle = 'rgba(61,96,112,0.25)'; ctx.lineWidth = 0.5; ctx.setLineDash([2, 3]);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(pad.l + cw, y); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(61,96,112,0.6)'; ctx.font = '8px Share Tech Mono'; ctx.textAlign = 'left';
      ctx.fillText(fmt(maxV * f), 0, y + 3);
    });
    // One point has no line to draw: put it in the middle as a dot
    const xAt = i => pts.length === 1 ? pad.l + cw / 2 : pad.l + i * (cw / (pts.length - 1));
    const yAt = v => pad.t + ch * (1 - v / maxV);
    if (pts.length === 1) {
      ctx.fillStyle = color; ctx.beginPath(); ctx.arc(xAt(0), yAt(pts[0]), 3, 0, 2 * Math.PI); ctx.fill();
    }
    const fillColor = color.replace(/[\d.]+\)$/, '0.15)');
    const grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + ch);
    grad.addColorStop(0, fillColor); grad.addColorStop(1, 'rgba(0,0,0,0)');
    if (pts.length > 1) {
      ctx.fillStyle = grad; ctx.beginPath();
      pts.forEach((v, i) => (i === 0 ? ctx.moveTo(xAt(i), yAt(v)) : ctx.lineTo(xAt(i), yAt(v))));
      ctx.lineTo(xAt(pts.length - 1), pad.t + ch); ctx.lineTo(pad.l, pad.t + ch); ctx.closePath(); ctx.fill();
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
      pts.forEach((v, i) => (i === 0 ? ctx.moveTo(xAt(i), yAt(v)) : ctx.lineTo(xAt(i), yAt(v))));
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(61,96,112,0.6)'; ctx.font = '7px Share Tech Mono'; ctx.textAlign = 'center';
    labels.forEach((l, i) => {
      if (i % Math.ceil(labels.length / 8) === 0) {
        ctx.fillText(String(l).slice(5), xAt(i), height - 5);
      }
    });
  }, [data, color, height, yFormat]);
  return <canvas ref={ref} className="chart" height={height} />;
}
