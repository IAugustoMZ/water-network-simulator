import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { AlertTriangle, Info, XCircle, Activity, Droplets, Gauge } from 'lucide-react';
import { useSimulationStore } from '../../store/simulationStore';
import type { SimulationWarning } from '../../types/network';

type Tab = 'overview' | 'nodes' | 'edges' | 'pumps' | 'valves' | 'tanks';

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'nodes',    label: 'Nodes' },
  { id: 'edges',    label: 'Edges' },
  { id: 'pumps',    label: 'Pumps' },
  { id: 'valves',   label: 'Valves' },
  { id: 'tanks',    label: 'Tanks' },
];

function WarningBadge({ w }: { w: SimulationWarning }) {
  const styles = {
    critical: 'bg-red-900/60 text-red-300 border-red-700',
    warning:  'bg-yellow-900/60 text-yellow-300 border-yellow-700',
    info:     'bg-blue-900/60 text-blue-300 border-blue-700',
  };
  const Icon = w.severity === 'critical' ? XCircle : w.severity === 'warning' ? AlertTriangle : Info;
  return (
    <div className={`flex items-start gap-1.5 text-xs rounded border px-2 py-1 ${styles[w.severity]}`}>
      <Icon size={12} className="shrink-0 mt-0.5" />
      <span>{w.message}</span>
    </div>
  );
}

function MetricCard({ label, value, unit, highlight }: { label: string; value: string; unit?: string; highlight?: boolean }) {
  return (
    <div className={`rounded p-3 ${highlight ? 'bg-red-900/40 border border-red-700' : 'bg-slate-700'}`}>
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className="text-lg font-bold text-slate-100">
        {value} <span className="text-sm font-normal text-slate-400">{unit}</span>
      </div>
    </div>
  );
}

const ResultsDashboard: React.FC = () => {
  const result = useSimulationStore((s) => s.result);
  const [tab, setTab] = useState<Tab>('overview');
  const [sortKey, setSortKey] = useState<string>('');
  const [sortAsc, setSortAsc] = useState(true);

  if (!result) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        Run a simulation to see results here.
      </div>
    );
  }

  const m = result.system_metrics;

  function handleSort(key: string) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(true); }
  }

  function SortTh({ label, k }: { label: string; k: string }) {
    return (
      <th
        className="px-2 py-1.5 text-left cursor-pointer hover:text-blue-400 whitespace-nowrap"
        onClick={() => handleSort(k)}
      >
        {label} {sortKey === k ? (sortAsc ? '↑' : '↓') : ''}
      </th>
    );
  }

  // ── Overview ──────────────────────────────────────────────────────────────
  const OverviewTab = () => (
    <div className="space-y-4">
      {/* Convergence status */}
      <div className={`rounded p-3 border ${result.status === 'converged' ? 'bg-green-900/30 border-green-700 text-green-300' : 'bg-red-900/30 border-red-700 text-red-300'}`}>
        <div className="flex items-center gap-2 font-semibold">
          <Activity size={16} />
          {result.status === 'converged' ? 'Converged' : 'Did Not Converge'}
        </div>
        <div className="text-xs mt-1 text-slate-400">
          Iterations: {result.iterations} · Residual: {result.residual_norm.toExponential(2)} m³/s · Scenario: {result.scenario_name}
        </div>
      </div>

      {/* Key metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        <MetricCard label="Total Demand" value={(m.total_demand * 1000).toFixed(1)} unit="L/s" />
        <MetricCard label="Total Power" value={m.total_power_kw.toFixed(1)} unit="kW" />
        <MetricCard label="Min Pressure" value={m.min_pressure_m.toFixed(1)} unit="m" highlight={m.min_pressure_m < 10} />
        <MetricCard label="Max Pressure" value={m.max_pressure_m.toFixed(1)} unit="m" />
        <MetricCard label="System Efficiency" value={(m.system_efficiency * 100).toFixed(1)} unit="%" />
        <MetricCard label="Mass Balance Error" value={m.mass_balance_error.toExponential(2)} unit="m³/s" />
      </div>

      {/* Warnings */}
      {result.warnings.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Warnings ({result.warnings.length})
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {result.warnings.map((w, i) => <WarningBadge key={i} w={w} />)}
          </div>
        </div>
      )}

      {/* Alerts summary */}
      {m.low_pressure_nodes.length > 0 && (
        <div className="text-xs bg-orange-900/30 border border-orange-700 rounded p-2 text-orange-300">
          <strong>Low pressure nodes:</strong> {m.low_pressure_nodes.join(', ')}
        </div>
      )}
      {m.flow_reversals.length > 0 && (
        <div className="text-xs bg-yellow-900/30 border border-yellow-700 rounded p-2 text-yellow-300">
          <strong>Flow reversals:</strong> {m.flow_reversals.join(', ')}
        </div>
      )}
      {m.bottleneck_edges.length > 0 && (
        <div className="text-xs bg-red-900/30 border border-red-700 rounded p-2 text-red-300">
          <strong>Bottleneck edges:</strong> {m.bottleneck_edges.join(', ')}
        </div>
      )}

      {/* Pressure distribution chart */}
      <div>
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
          Pressure Distribution (Junction Nodes)
        </div>
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={result.nodes.filter(n => n.node_type === 'junction').slice(0, 30).map(n => ({ id: n.node_id.replace('J', ''), p: parseFloat(n.pressure_m.toFixed(1)) }))}>
            <XAxis dataKey="id" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={2} />
            <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} />
            <Tooltip formatter={(v) => [`${v} m`, 'Pressure']} contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', fontSize: 11 }} />
            <ReferenceLine y={10} stroke="#f97316" strokeDasharray="3 3" />
            <Bar dataKey="p" radius={[2, 2, 0, 0]}>
              {result.nodes.filter(n => n.node_type === 'junction').slice(0, 30).map((n, i) => (
                <Cell key={i} fill={n.pressure_m < 10 ? '#ef4444' : n.pressure_m < 25 ? '#22c55e' : '#3b82f6'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  // ── Nodes ─────────────────────────────────────────────────────────────────
  const NodesTab = () => {
    const sorted = [...result.nodes].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    return (
      <div className="overflow-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-700 text-slate-400 sticky top-0">
            <tr>
              <SortTh label="Node" k="node_id" />
              <SortTh label="Type" k="node_type" />
              <SortTh label="Elev (m)" k="elevation" />
              <SortTh label="Head (m)" k="hydraulic_head" />
              <SortTh label="P (m)" k="pressure_m" />
              <SortTh label="P (kPa)" k="pressure_kpa" />
              <SortTh label="Demand (L/s)" k="demand" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((n) => (
              <tr key={n.node_id} className={`border-b border-slate-700 hover:bg-slate-700/50 ${n.pressure_m < 10 && n.node_type === 'junction' ? 'bg-red-900/20' : ''}`}>
                <td className="px-2 py-1 font-mono">{n.node_id}</td>
                <td className="px-2 py-1 text-slate-400">{n.node_type}</td>
                <td className="px-2 py-1">{n.elevation.toFixed(1)}</td>
                <td className="px-2 py-1">{n.hydraulic_head.toFixed(2)}</td>
                <td className={`px-2 py-1 font-semibold ${n.pressure_m < 10 ? 'text-red-400' : 'text-green-400'}`}>{n.pressure_m.toFixed(2)}</td>
                <td className="px-2 py-1">{n.pressure_kpa.toFixed(1)}</td>
                <td className="px-2 py-1">{(n.demand * 1000).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // ── Edges ─────────────────────────────────────────────────────────────────
  const EdgesTab = () => {
    const sorted = [...result.edges].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av;
      return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    return (
      <div className="overflow-auto">
        <table className="w-full text-xs">
          <thead className="bg-slate-700 text-slate-400 sticky top-0">
            <tr>
              <SortTh label="Edge" k="edge_id" />
              <SortTh label="Type" k="edge_type" />
              <SortTh label="Flow (L/s)" k="flow_lps" />
              <SortTh label="V (m/s)" k="velocity" />
              <SortTh label="ΔH (m)" k="head_loss" />
              <SortTh label="Re" k="reynolds" />
              <SortTh label="Status" k="status" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((e) => (
              <tr key={e.edge_id} className={`border-b border-slate-700 hover:bg-slate-700/50 ${e.velocity > 2.5 ? 'bg-red-900/20' : ''}`}>
                <td className="px-2 py-1 font-mono">{e.edge_id}</td>
                <td className="px-2 py-1 text-slate-400">{e.edge_type}</td>
                <td className={`px-2 py-1 ${e.is_reversed ? 'text-yellow-400' : ''}`}>{e.flow_lps.toFixed(2)}{e.is_reversed ? ' ↩' : ''}</td>
                <td className={`px-2 py-1 ${e.velocity > 2.5 ? 'text-red-400 font-semibold' : ''}`}>{e.velocity.toFixed(2)}</td>
                <td className="px-2 py-1">{e.head_loss.toFixed(2)}</td>
                <td className="px-2 py-1">{e.reynolds > 0 ? e.reynolds.toFixed(0) : '—'}</td>
                <td className="px-2 py-1 text-slate-400">{e.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // ── Pumps ─────────────────────────────────────────────────────────────────
  const PumpsTab = () => (
    <div className="space-y-3">
      {result.pumps.map((p) => (
        <div key={p.pump_id} className={`rounded p-3 border ${p.is_cavitating ? 'bg-red-900/30 border-red-600' : p.is_on ? 'bg-slate-700 border-slate-600' : 'bg-slate-800 border-slate-700 opacity-60'}`}>
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-sm">{p.pump_id}</span>
            <div className="flex gap-2 text-xs">
              <span className={`px-2 py-0.5 rounded font-semibold ${p.is_on ? 'bg-green-700 text-green-200' : 'bg-slate-600 text-slate-400'}`}>
                {p.is_on ? 'ON' : 'OFF'}
              </span>
              {p.is_cavitating && (
                <span className="px-2 py-0.5 rounded bg-red-700 text-red-200 font-semibold">CAVITATING</span>
              )}
            </div>
          </div>
          {p.is_on && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <span className="text-slate-400">Flow</span><span>{p.flow_lps.toFixed(2)} L/s</span>
              <span className="text-slate-400">Head</span><span>{p.head.toFixed(1)} m</span>
              <span className="text-slate-400">Speed</span><span>{(p.speed_ratio * 100).toFixed(0)} %</span>
              <span className="text-slate-400">Efficiency</span><span>{(p.efficiency * 100).toFixed(1)} %</span>
              <span className="text-slate-400">Power</span><span>{p.power_kw.toFixed(2)} kW</span>
              <span className="text-slate-400">NPSHa</span><span>{p.npsha.toFixed(2)} m</span>
              <span className="text-slate-400">NPSHr</span><span>{p.npshr.toFixed(2)} m</span>
              <span className={`text-slate-400`}>NPSH Margin</span>
              <span className={p.cavitation_margin < 0 ? 'text-red-400 font-semibold' : 'text-green-400'}>
                {p.cavitation_margin.toFixed(2)} m
              </span>
            </div>
          )}
          {/* NPSH bar */}
          {p.is_on && (
            <div className="mt-2">
              <div className="text-xs text-slate-400 mb-1">NPSH Available vs Required</div>
              <ResponsiveContainer width="100%" height={50}>
                <BarChart data={[{ name: 'NPSHa', v: p.npsha }, { name: 'NPSHr', v: p.npshr }]} layout="vertical">
                  <XAxis type="number" tick={{ fontSize: 9 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 9 }} width={40} />
                  <Tooltip formatter={(v) => [`${Number(v).toFixed(2)} m`]} contentStyle={{ fontSize: 10, backgroundColor: '#1e293b', border: '1px solid #475569' }} />
                  <Bar dataKey="v" radius={[0, 3, 3, 0]}>
                    <Cell fill="#3b82f6" />
                    <Cell fill={p.is_cavitating ? '#ef4444' : '#22c55e'} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      ))}
    </div>
  );

  // ── Valves ────────────────────────────────────────────────────────────────
  const ValvesTab = () => (
    <div className="overflow-auto">
      <table className="w-full text-xs">
        <thead className="bg-slate-700 text-slate-400 sticky top-0">
          <tr>
            <th className="px-2 py-1.5 text-left">Valve</th>
            <th className="px-2 py-1.5 text-left">Type</th>
            <th className="px-2 py-1.5 text-left">Flow (L/s)</th>
            <th className="px-2 py-1.5 text-left">ΔP (m)</th>
            <th className="px-2 py-1.5 text-left">Opening (%)</th>
            <th className="px-2 py-1.5 text-left">Status</th>
          </tr>
        </thead>
        <tbody>
          {result.valves.map((v) => (
            <tr key={v.valve_id} className="border-b border-slate-700 hover:bg-slate-700/50">
              <td className="px-2 py-1 font-mono">{v.valve_id}</td>
              <td className="px-2 py-1 text-slate-400 uppercase text-xs">{v.valve_type}</td>
              <td className="px-2 py-1">{v.flow_lps.toFixed(2)}</td>
              <td className="px-2 py-1">{v.pressure_drop_m.toFixed(2)}</td>
              <td className="px-2 py-1">
                <div className="flex items-center gap-1">
                  <div className="flex-1 bg-slate-600 rounded-full h-1.5">
                    <div className="bg-amber-400 rounded-full h-1.5" style={{ width: `${v.opening_fraction * 100}%` }} />
                  </div>
                  <span>{(v.opening_fraction * 100).toFixed(0)}</span>
                </div>
              </td>
              <td className="px-2 py-1 text-slate-400">{v.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  // ── Tanks ─────────────────────────────────────────────────────────────────
  const TanksTab = () => (
    <div className="space-y-3">
      {result.tanks.map((t) => (
        <div key={t.tank_id} className="bg-slate-700 rounded p-3">
          <div className="flex items-center gap-2 mb-2">
            <Droplets size={16} className="text-blue-400" />
            <span className="font-semibold">{t.tank_id}</span>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <span className="text-slate-400">Water Level</span><span>{t.water_level.toFixed(2)} m</span>
            <span className="text-slate-400">Hydraulic Head</span><span>{t.hydraulic_head.toFixed(2)} m</span>
            <span className="text-slate-400">Net Outflow</span><span>{(t.outflow * 1000).toFixed(2)} L/s</span>
            <span className="text-slate-400">Residence Time</span>
            <span>{t.residence_time === Infinity || t.residence_time > 1e6 ? '∞' : `${(t.residence_time / 3600).toFixed(1)} h`}</span>
          </div>
        </div>
      ))}
      {result.tanks.length === 0 && (
        <p className="text-slate-500 text-sm text-center py-4">No tank results.</p>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-slate-800">
      {/* Tab bar */}
      <div className="flex border-b border-slate-700 overflow-x-auto shrink-0">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap transition-colors ${
              tab === t.id
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-3">
        {tab === 'overview' && <OverviewTab />}
        {tab === 'nodes'    && <NodesTab />}
        {tab === 'edges'    && <EdgesTab />}
        {tab === 'pumps'    && <PumpsTab />}
        {tab === 'valves'   && <ValvesTab />}
        {tab === 'tanks'    && <TanksTab />}
      </div>
    </div>
  );
};

export default ResultsDashboard;
