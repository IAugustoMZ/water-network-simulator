import React from 'react';
import { Play, RotateCcw, Loader2, AlertCircle, CheckCircle2, Zap } from 'lucide-react';
import { useSimulationStore, SCENARIOS, SCENARIO_LABELS } from '../../store/simulationStore';

const PUMP_IDS = ['PUMP1', 'PUMP2', 'PUMP3', 'BOOST1'];
const CONTROL_VALVE_IDS = ['PRV01', 'PRV02', 'PRV03', 'PRV04', 'PRV05', 'PRV06', 'FCV01', 'FCV02', 'FCV03', 'FCV04'];

const ControlPanel: React.FC = () => {
  const {
    currentScenario, overrides, isLoading, error, result, backendOnline,
    setScenario, setPumpOn, setPumpSpeed, setValveOpening,
    setGlobalDemandMultiplier, runSimulation, resetOverrides,
  } = useSimulationStore();

  const getPumpState = (id: string) => ({
    isOn: overrides.pumps[id]?.is_on ?? true,
    speed: overrides.pumps[id]?.speed_ratio ?? 1.0,
  });

  const getValveOpening = (id: string) =>
    overrides.valves[id]?.opening_fraction ?? 1.0;

  return (
    <div className="flex flex-col h-full bg-slate-800 text-slate-200 overflow-y-auto">
      {/* Header */}
      <div className="px-4 py-3 bg-slate-900 border-b border-slate-700 flex items-center gap-2">
        <Zap size={18} className="text-blue-400" />
        <span className="font-semibold text-sm">Simulation Controls</span>
        <div className={`ml-auto w-2 h-2 rounded-full ${backendOnline ? 'bg-green-400' : 'bg-red-400'}`} title={backendOnline ? 'Backend online' : 'Backend offline'} />
      </div>

      <div className="flex-1 p-3 space-y-4">
        {/* Scenario selector */}
        <section>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
            Scenario
          </label>
          <select
            value={currentScenario}
            onChange={(e) => setScenario(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {SCENARIOS.map((s) => (
              <option key={s} value={s}>{SCENARIO_LABELS[s]}</option>
            ))}
          </select>
        </section>

        {/* Pump controls */}
        <section>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Pumps
          </label>
          <div className="space-y-3">
            {PUMP_IDS.map((id) => {
              const { isOn, speed } = getPumpState(id);
              return (
                <div key={id} className="bg-slate-700 rounded p-2.5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium">{id}</span>
                    <button
                      onClick={() => setPumpOn(id, !isOn)}
                      className={`px-2.5 py-0.5 rounded text-xs font-semibold transition-colors ${
                        isOn ? 'bg-green-600 hover:bg-green-700' : 'bg-red-700 hover:bg-red-800'
                      }`}
                    >
                      {isOn ? 'ON' : 'OFF'}
                    </button>
                  </div>
                  {isOn && (
                    <div>
                      <div className="flex justify-between text-xs text-slate-400 mb-1">
                        <span>Speed</span>
                        <span>{(speed * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min={50} max={120} step={1}
                        value={Math.round(speed * 100)}
                        onChange={(e) => setPumpSpeed(id, parseInt(e.target.value) / 100)}
                        className="w-full accent-blue-500"
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* Valve controls (control valves only) */}
        <section>
          <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
            Control Valves
          </label>
          <div className="space-y-2">
            {CONTROL_VALVE_IDS.map((id) => {
              const opening = getValveOpening(id);
              return (
                <div key={id} className="bg-slate-700 rounded p-2">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium">{id}</span>
                    <span className="text-slate-400">{(opening * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min={0} max={100} step={1}
                    value={Math.round(opening * 100)}
                    onChange={(e) => setValveOpening(id, parseInt(e.target.value) / 100)}
                    className="w-full accent-amber-500"
                  />
                </div>
              );
            })}
          </div>
        </section>

        {/* Global demand */}
        <section>
          <div className="flex justify-between text-xs mb-1">
            <label className="font-semibold text-slate-400 uppercase tracking-wide">
              Global Demand
            </label>
            <span className="text-slate-300">{(overrides.global_demand_multiplier * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min={50} max={200} step={5}
            value={Math.round(overrides.global_demand_multiplier * 100)}
            onChange={(e) => setGlobalDemandMultiplier(parseInt(e.target.value) / 100)}
            className="w-full accent-purple-500"
          />
        </section>
      </div>

      {/* Footer: actions + status */}
      <div className="p-3 border-t border-slate-700 space-y-2">
        {error && (
          <div className="flex items-start gap-1.5 text-xs text-red-400 bg-red-900/30 rounded p-2">
            <AlertCircle size={14} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {result && !isLoading && (
          <div className="flex items-center gap-1.5 text-xs text-green-400">
            <CheckCircle2 size={14} />
            <span>
              {result.status === 'converged' ? 'Converged' : 'Diverged'} in {result.iterations} iterations
            </span>
          </div>
        )}
        <div className="flex gap-2">
          <button
            onClick={resetOverrides}
            disabled={isLoading}
            className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-600 hover:bg-slate-500 rounded text-xs font-medium transition-colors disabled:opacity-50"
          >
            <RotateCcw size={13} />
            Reset
          </button>
          <button
            onClick={runSimulation}
            disabled={isLoading || !backendOnline}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 disabled:opacity-60 rounded text-sm font-semibold transition-colors"
          >
            {isLoading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            {isLoading ? 'Solving…' : 'Run Simulation'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ControlPanel;
