import React, { useEffect, useState } from 'react';
import {
  ComposedChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceDot, ReferenceLine, Area, BarChart, Bar, Cell,
} from 'recharts';
import { Activity, AlertTriangle, Zap, Gauge, Droplets, ArrowLeft } from 'lucide-react';
import { useSimulationStore } from '../../store/simulationStore';
import { api } from '../../services/api';
import type { PumpCurveData, PumpResult, SpeedCurve, EfficiencyContour } from '../../types/network';

interface Props { onBack: () => void }

// ── helpers ────────────────────────────────────────────────────────────────

const CHART_TIP = {
  backgroundColor: '#1e293b',
  border: '1px solid #475569',
  fontSize: 11,
  borderRadius: 6,
};

const intTick = (v: number) => Math.round(v).toString();

function speedColor(n: number, isCurrent: boolean): string {
  if (isCurrent) return '#f59e0b';
  const t = Math.max(0, Math.min(1, (n - 0.4) / 0.6));
  const l = Math.round(35 + t * 35);
  return `hsl(215, 14%, ${l}%)`;
}

function KpiCard({ label, value, unit, warn }: { label: string; value: string; unit?: string; warn?: boolean }) {
  return (
    <div className={`rounded-lg p-3 ${warn ? 'bg-red-900/40 border border-red-700' : 'bg-slate-700/60'}`}>
      <div className="text-[10px] text-slate-400 uppercase tracking-wider mb-0.5">{label}</div>
      <div className="text-lg font-bold">
        {value}{unit && <span className="text-xs font-normal text-slate-400 ml-1">{unit}</span>}
      </div>
    </div>
  );
}

function Badge({ label, color }: { label: string; color: string }) {
  return <span className={`px-2 py-0.5 rounded text-xs font-semibold ${color}`}>{label}</span>;
}

// ── Main component ──────────────────────────────────────────────────────────

const PumpMonitoringDashboard: React.FC<Props> = ({ onBack }) => {
  const { result, networkId } = useSimulationStore();
  const [curves, setCurves] = useState<PumpCurveData[]>([]);
  const [selectedPump, setSelectedPump] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!networkId) return;
    setLoading(true);
    setError(null);
    api.getPumpCurves(networkId)
      .then((data) => {
        setCurves(data);
        if (data.length > 0 && !selectedPump) setSelectedPump(data[0].pump_id);
      })
      .catch((e) => setError(e?.message || 'Failed to load pump curves'))
      .finally(() => setLoading(false));
  }, [networkId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!result) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        Run a simulation first to view pump monitoring data.
      </div>
    );
  }

  const pumpResult: PumpResult | undefined = result.pumps.find((p) => p.pump_id === selectedPump);
  const curveData: PumpCurveData | undefined = curves.find((c) => c.pump_id === selectedPump);

  // domains for vendor chart
  const allFlows = curveData?.speed_curves.flatMap((sc) => sc.points.map((p) => p.flow_lps)) ?? [];
  const allHeads = curveData?.speed_curves.flatMap((sc) => sc.points.map((p) => p.head)) ?? [];
  const xMax = allFlows.length ? Math.ceil(Math.max(...allFlows) / 5) * 5 : 100;
  const yMax = allHeads.length ? Math.ceil(Math.max(...allHeads) / 5) * 5 : 80;

  // detail chart data
  const effData = curveData?.rated_curve.map((pt, i) => ({
    flow: pt.flow_lps,
    rated_eff: pt.efficiency * 100,
    current_eff: (curveData.current_curve[i]?.efficiency ?? 0) * 100,
  })) ?? [];

  const powerData = curveData?.rated_curve.map((pt, i) => ({
    flow: pt.flow_lps,
    rated_power: pt.power_kw,
    current_power: curveData.current_curve[i]?.power_kw ?? null,
  })) ?? [];

  const npshData = curveData?.current_curve.map((pt) => ({
    flow: pt.flow_lps,
    npshr: pt.npsh_required,
  })) ?? [];

  // label positions
  const contourLabelPts = (curveData?.efficiency_contours ?? []).map((ec: EfficiencyContour) => {
    const top = ec.points.reduce((m, p) => (p.head > m.head ? p : m), ec.points[0] ?? { flow_lps: 0, head: 0 });
    return { label: ec.label, flow_lps: top.flow_lps, head: top.head };
  });
  const speedLabelPts = (curveData?.speed_curves ?? []).map((sc: SpeedCurve) => {
    const last = sc.points[sc.points.length - 1] ?? { flow_lps: 0, head: 0 };
    return { label: sc.label, flow_lps: last.flow_lps, head: last.head, isCurrent: sc.is_current };
  });

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2 bg-slate-800 border-b border-slate-700 shrink-0">
        <button onClick={onBack} className="flex items-center gap-1 text-xs text-slate-400 hover:text-blue-400 transition-colors">
          <ArrowLeft size={14} /> Back to Simulator
        </button>
        <div className="h-4 w-px bg-slate-600" />
        <Gauge size={16} className="text-purple-400" />
        <span className="font-semibold text-sm">Pump Monitoring Dashboard</span>
        <span className="text-xs text-slate-500">| Scenario: <span className="text-blue-300">{result.scenario_name}</span></span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Pump selector */}
        <div className="w-52 shrink-0 border-r border-slate-700 overflow-y-auto">
          <div className="px-3 py-2 text-[10px] text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-700">
            Pumps ({result.pumps.length})
          </div>
          {result.pumps.map((p) => (
            <button
              key={p.pump_id}
              onClick={() => setSelectedPump(p.pump_id)}
              className={`w-full text-left px-3 py-2.5 border-b border-slate-700/50 transition-colors ${
                selectedPump === p.pump_id ? 'bg-blue-900/30 border-l-2 border-l-blue-400' : 'hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm font-semibold">{p.pump_id}</span>
                <div className="flex gap-1">
                  <Badge label={p.is_on ? 'ON' : 'OFF'} color={p.is_on ? 'bg-green-700/60 text-green-300' : 'bg-slate-600 text-slate-400'} />
                  {p.is_cavitating && <Badge label="CAV" color="bg-red-700/60 text-red-300" />}
                </div>
              </div>
              {p.is_on && (
                <div className="text-[10px] text-slate-400 mt-1">
                  {p.flow_lps.toFixed(1)} L/s · {p.head.toFixed(1)} m · {(p.efficiency * 100).toFixed(0)}%
                </div>
              )}
            </button>
          ))}
        </div>

        {/* Charts area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading && <div className="text-center text-slate-500 py-8">Loading pump curves…</div>}
          {error && <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-300">{error}</div>}

          {pumpResult && !loading && (
            <>
              {/* KPI strip */}
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
                <KpiCard label="Flow" value={pumpResult.is_on ? pumpResult.flow_lps.toFixed(2) : '—'} unit="L/s" />
                <KpiCard label="Head" value={pumpResult.is_on ? pumpResult.head.toFixed(1) : '—'} unit="m" />
                <KpiCard label="Speed" value={(pumpResult.speed_ratio * 100).toFixed(0)} unit="%" />
                <KpiCard label="Efficiency" value={pumpResult.is_on ? (pumpResult.efficiency * 100).toFixed(1) : '—'} unit="%" />
                <KpiCard label="Power" value={pumpResult.is_on ? pumpResult.power_kw.toFixed(2) : '—'} unit="kW" />
                <KpiCard label="NPSHa" value={pumpResult.is_on ? pumpResult.npsha.toFixed(2) : '—'} unit="m" />
                <KpiCard label="NPSH Margin" value={pumpResult.is_on ? pumpResult.cavitation_margin.toFixed(2) : '—'} unit="m"
                  warn={pumpResult.is_on && pumpResult.cavitation_margin < 0} />
              </div>

              {pumpResult.is_cavitating && (
                <div className="flex items-center gap-2 bg-red-900/40 border border-red-600 rounded-lg p-3 text-sm text-red-300">
                  <AlertTriangle size={16} />
                  <span><strong>Cavitation detected!</strong> NPSHa ({pumpResult.npsha.toFixed(2)} m)
                    &lt; NPSHr ({pumpResult.npshr.toFixed(2)} m) — margin: {pumpResult.cavitation_margin.toFixed(2)} m</span>
                </div>
              )}

              {/* ═══ VENDOR-STYLE H-Q CHART ═══ */}
              {curveData && (
                <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <Activity size={14} className="text-blue-400" />
                    <span className="text-sm font-semibold">Head–Flow Characteristic (H-Q)</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mb-3">
                    <span className="text-slate-400 mr-3">― speed curves (grey→amber = 40%→current)</span>
                    <span className="text-green-400 mr-3">- - - iso-efficiency contours</span>
                    <span className="text-amber-400">● operating point</span>
                  </div>
                  <ResponsiveContainer width="100%" height={310}>
                    <ComposedChart margin={{ top: 10, right: 64, bottom: 32, left: 20 }}>
                      <XAxis type="number" dataKey="flow_lps" domain={[0, xMax]} tickCount={9}
                        tickFormatter={intTick}
                        label={{ value: 'Flow (L/s)', position: 'insideBottom', offset: -16, fontSize: 11, fill: '#94a3b8' }}
                        tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <YAxis type="number" dataKey="head" domain={[0, yMax]} tickCount={7}
                        tickFormatter={intTick}
                        label={{ value: 'Head (m)', angle: -90, position: 'insideLeft', offset: 10, fontSize: 11, fill: '#94a3b8' }}
                        tick={{ fontSize: 10, fill: '#94a3b8' }} />
                      <Tooltip contentStyle={CHART_TIP}
                        formatter={(v: number) => [v.toFixed(2), '']}
                        labelFormatter={(v: number) => `Q = ${Math.round(v)} L/s`} />

                      {/* Iso-efficiency contours (draw first = bottom layer) */}
                      {curveData.efficiency_contours.map((ec) => (
                        <Line key={`ec-${ec.efficiency}`} data={ec.points} dataKey="head"
                          type="monotone" stroke="#4ade80" strokeWidth={1} strokeDasharray="5 4"
                          dot={false} activeDot={false} legendType="none" />
                      ))}

                      {/* Speed curves (non-current under current) */}
                      {[...curveData.speed_curves]
                        .sort((a, b) => (a.is_current ? 1 : 0) - (b.is_current ? 1 : 0))
                        .map((sc) => (
                          <Line key={`sc-${sc.speed_ratio}`} data={sc.points} dataKey="head"
                            type="monotone" stroke={speedColor(sc.speed_ratio, sc.is_current)}
                            strokeWidth={sc.is_current ? 2.5 : 1.5} dot={false} activeDot={false} legendType="none" />
                        ))}

                      {/* Efficiency contour labels at top of each contour */}
                      {contourLabelPts.map((lp) => (
                        <ReferenceDot key={`ecl-${lp.label}`} x={lp.flow_lps} y={lp.head} r={0}
                          label={{ value: lp.label, position: 'insideTopRight', fontSize: 9, fill: '#4ade80' }} />
                      ))}

                      {/* Speed curve end-labels */}
                      {speedLabelPts.map((lp) => (
                        <ReferenceDot key={`scl-${lp.label}`} x={lp.flow_lps} y={lp.head} r={0}
                          label={{ value: lp.label, position: 'right', fontSize: 9, fill: lp.isCurrent ? '#f59e0b' : '#64748b' }} />
                      ))}

                      {/* Operating point */}
                      {pumpResult.is_on && (
                        <ReferenceDot x={pumpResult.flow_lps} y={pumpResult.head} r={7}
                          fill="#f59e0b" stroke="#fff" strokeWidth={2}
                          label={{ value: 'OP', position: 'top', fontSize: 10, fill: '#f59e0b' }} />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* ═══ EFFICIENCY CURVE ═══ */}
              {curveData && (
                <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Gauge size={14} className="text-green-400" />
                    <span className="text-sm font-semibold">Efficiency Curve (η-Q)</span>
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <ComposedChart data={effData} margin={{ top: 5, right: 20, bottom: 28, left: 20 }}>
                      <XAxis dataKey="flow" tickFormatter={intTick} tick={{ fontSize: 10, fill: '#94a3b8' }}
                        label={{ value: 'Flow (L/s)', position: 'insideBottom', offset: -14, fontSize: 11, fill: '#94a3b8' }} />
                      <YAxis domain={[0, 100]} tickFormatter={intTick} tick={{ fontSize: 10, fill: '#94a3b8' }}
                        label={{ value: 'η (%)', angle: -90, position: 'insideLeft', offset: 10, fontSize: 11, fill: '#94a3b8' }} />
                      <Tooltip contentStyle={CHART_TIP} formatter={(v: number) => [`${v.toFixed(1)} %`, '']} />
                      <Area type="monotone" dataKey="rated_eff" name="Rated (100%)"
                        stroke="#64748b" fill="#64748b" fillOpacity={0.06} strokeDasharray="6 3" strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="current_eff" name={`${(curveData.speed_ratio * 100).toFixed(0)}%`}
                        stroke="#22c55e" strokeWidth={2.5} dot={false} />
                      {pumpResult.is_on && (
                        <ReferenceDot x={pumpResult.flow_lps} y={pumpResult.efficiency * 100} r={6}
                          fill="#f59e0b" stroke="#fff" strokeWidth={2}
                          label={{ value: 'OP', position: 'top', fontSize: 10, fill: '#f59e0b' }} />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* ═══ POWER CURVE ═══ */}
              {curveData && (
                <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Zap size={14} className="text-amber-400" />
                    <span className="text-sm font-semibold">Power Curve (P-Q)</span>
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <ComposedChart data={powerData} margin={{ top: 5, right: 20, bottom: 28, left: 20 }}>
                      <XAxis dataKey="flow" tickFormatter={intTick} tick={{ fontSize: 10, fill: '#94a3b8' }}
                        label={{ value: 'Flow (L/s)', position: 'insideBottom', offset: -14, fontSize: 11, fill: '#94a3b8' }} />
                      <YAxis tickFormatter={(v) => v.toFixed(1)} tick={{ fontSize: 10, fill: '#94a3b8' }}
                        label={{ value: 'P (kW)', angle: -90, position: 'insideLeft', offset: 10, fontSize: 11, fill: '#94a3b8' }} />
                      <Tooltip contentStyle={CHART_TIP} formatter={(v: number) => [`${v.toFixed(2)} kW`, '']} />
                      <Area type="monotone" dataKey="rated_power" name="Rated (100%)"
                        stroke="#64748b" fill="#64748b" fillOpacity={0.06} strokeDasharray="6 3" strokeWidth={1.5} dot={false} />
                      <Line type="monotone" dataKey="current_power" name={`${(curveData.speed_ratio * 100).toFixed(0)}%`}
                        stroke="#f59e0b" strokeWidth={2.5} dot={false} />
                      {pumpResult.is_on && (
                        <ReferenceDot x={pumpResult.flow_lps} y={pumpResult.power_kw} r={6}
                          fill="#ef4444" stroke="#fff" strokeWidth={2}
                          label={{ value: 'OP', position: 'top', fontSize: 10, fill: '#ef4444' }} />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* ═══ NPSH ANALYSIS ═══ */}
              {curveData && (
                <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Droplets size={14} className="text-cyan-400" />
                    <span className="text-sm font-semibold">NPSH Analysis</span>
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs text-slate-400 mb-2">NPSHr vs Flow (current speed)</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <ComposedChart data={npshData} margin={{ top: 5, right: 20, bottom: 28, left: 20 }}>
                          <XAxis dataKey="flow" tickFormatter={intTick} tick={{ fontSize: 10, fill: '#94a3b8' }}
                            label={{ value: 'Flow (L/s)', position: 'insideBottom', offset: -14, fontSize: 11, fill: '#94a3b8' }} />
                          <YAxis tickFormatter={(v) => v.toFixed(1)} tick={{ fontSize: 10, fill: '#94a3b8' }}
                            label={{ value: 'NPSH (m)', angle: -90, position: 'insideLeft', offset: 10, fontSize: 11, fill: '#94a3b8' }} />
                          <Tooltip contentStyle={CHART_TIP} formatter={(v: number) => [`${v.toFixed(2)} m`, '']} />
                          <Line type="monotone" dataKey="npshr" name="NPSHr" stroke="#ef4444" strokeWidth={2} dot={false} />
                          {pumpResult.is_on && (
                            <>
                              <ReferenceLine y={pumpResult.npsha} stroke="#3b82f6" strokeDasharray="6 3"
                                label={{ value: `NPSHa = ${pumpResult.npsha.toFixed(1)} m`, position: 'insideTopLeft', fontSize: 9, fill: '#3b82f6' }} />
                              <ReferenceDot x={pumpResult.flow_lps} y={pumpResult.npshr} r={5}
                                fill={pumpResult.is_cavitating ? '#ef4444' : '#22c55e'} stroke="#fff" strokeWidth={2} />
                            </>
                          )}
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400 mb-2">NPSHa vs NPSHr at operating point</div>
                      <ResponsiveContainer width="100%" height={180}>
                        <BarChart data={[
                          { name: 'NPSHa', value: pumpResult.npsha },
                          { name: 'NPSHr', value: pumpResult.npshr },
                          { name: 'Margin', value: Math.max(0, pumpResult.cavitation_margin) },
                        ]} margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
                          <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} tickFormatter={(v) => v.toFixed(1)} />
                          <Tooltip contentStyle={CHART_TIP} formatter={(v: number) => [`${v.toFixed(2)} m`, '']} />
                          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                            <Cell fill="#3b82f6" />
                            <Cell fill={pumpResult.is_cavitating ? '#ef4444' : '#f59e0b'} />
                            <Cell fill={pumpResult.cavitation_margin < 0 ? '#ef4444' : '#22c55e'} />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              )}

              {/* ═══ ALL PUMPS TABLE ═══ */}
              <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
                <div className="text-sm font-semibold mb-3">All Pumps Summary</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-700 text-slate-400">
                      <tr>
                        {['Pump','Status','Flow (L/s)','Head (m)','Speed (%)','η (%)','Power (kW)','NPSHa (m)','NPSHr (m)','Margin (m)'].map(h => (
                          <th key={h} className="px-3 py-1.5 text-left whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.pumps.map((p) => (
                        <tr key={p.pump_id} onClick={() => setSelectedPump(p.pump_id)}
                          className={`border-b border-slate-700 cursor-pointer transition-colors ${
                            p.pump_id === selectedPump ? 'bg-blue-900/20' : 'hover:bg-slate-700/50'
                          } ${p.is_cavitating ? 'bg-red-900/10' : ''}`}>
                          <td className="px-3 py-1.5 font-mono font-semibold">{p.pump_id}</td>
                          <td className="px-3 py-1.5">
                            {p.is_on
                              ? p.is_cavitating
                                ? <Badge label="CAVITATING" color="bg-red-700/60 text-red-300" />
                                : <Badge label="NORMAL" color="bg-green-700/60 text-green-300" />
                              : <Badge label="OFF" color="bg-slate-600 text-slate-400" />}
                          </td>
                          <td className="px-3 py-1.5">{p.is_on ? p.flow_lps.toFixed(1) : '—'}</td>
                          <td className="px-3 py-1.5">{p.is_on ? p.head.toFixed(1) : '—'}</td>
                          <td className="px-3 py-1.5">{(p.speed_ratio * 100).toFixed(0)}</td>
                          <td className="px-3 py-1.5">{p.is_on ? (p.efficiency * 100).toFixed(1) : '—'}</td>
                          <td className="px-3 py-1.5">{p.is_on ? p.power_kw.toFixed(2) : '—'}</td>
                          <td className="px-3 py-1.5">{p.is_on ? p.npsha.toFixed(2) : '—'}</td>
                          <td className="px-3 py-1.5">{p.is_on ? p.npshr.toFixed(2) : '—'}</td>
                          <td className={`px-3 py-1.5 font-semibold ${
                            p.is_on ? (p.cavitation_margin < 0 ? 'text-red-400' : 'text-green-400') : 'text-slate-500'
                          }`}>{p.is_on ? p.cavitation_margin.toFixed(2) : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {!pumpResult && !loading && (
            <div className="text-center text-slate-500 py-8">Select a pump from the left panel.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PumpMonitoringDashboard;
