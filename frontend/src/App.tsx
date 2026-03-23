import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Droplets, Server, AlertCircle, Gauge } from 'lucide-react';
import { useSimulationStore } from './store/simulationStore';
import NetworkGraph from './components/NetworkGraph';
import ControlPanel from './components/ControlPanel';
import ResultsDashboard from './components/ResultsDashboard';
import PumpMonitoringDashboard from './components/PumpMonitoringDashboard';
import AIAnalysisPanel from './components/AIAnalysisPanel';
import DragHandle from './components/DragHandle';

type Page = 'simulator' | 'pump-monitoring';

const MIN_PANEL_HEIGHT = 80;
const MAX_PANEL_FRACTION = 0.85;

const App: React.FC = () => {
  const { initialize, runSimulation, backendOnline, error, result } = useSimulationStore();
  const [page, setPage] = useState<Page>('simulator');
  const [bottomHeight, setBottomHeight] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    initialize().then(() => {
      runSimulation();
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleResize = useCallback((delta: number) => {
    setBottomHeight((prev) => {
      const container = containerRef.current;
      if (!container) return prev;
      const totalH = container.clientHeight;
      const maxH = totalH * MAX_PANEL_FRACTION;
      const current = prev ?? totalH * 0.4;
      return Math.max(MIN_PANEL_HEIGHT, Math.min(maxH, current + delta));
    });
  }, []);

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-100 overflow-hidden">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <header className="flex items-center gap-3 px-4 py-2 bg-slate-950 border-b border-slate-700 shrink-0">
        <Droplets size={22} className="text-blue-400" />
        <span className="font-bold text-base tracking-tight">Water Network Simulator</span>
        <span className="text-xs text-slate-500 ml-1">| High-Fidelity Steady-State Hydraulic Simulation</span>

        {/* ── Page navigation ── */}
        <nav className="flex items-center gap-1 ml-6">
          <button
            onClick={() => setPage('simulator')}
            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
              page === 'simulator'
                ? 'bg-blue-600/30 text-blue-300 border border-blue-500/40'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            Simulator
          </button>
          <button
            onClick={() => setPage('pump-monitoring')}
            className={`flex items-center gap-1 px-3 py-1 rounded text-xs font-medium transition-colors ${
              page === 'pump-monitoring'
                ? 'bg-purple-600/30 text-purple-300 border border-purple-500/40'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Gauge size={12} />
            Pump Monitoring
          </button>
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {result && (
            <span className="text-xs text-slate-400">
              {result.nodes.length} nodes · {result.edges.length} edges · scenario: <span className="text-blue-300">{result.scenario_name}</span>
            </span>
          )}
          <div className={`flex items-center gap-1.5 text-xs ${backendOnline ? 'text-green-400' : 'text-red-400'}`}>
            <Server size={13} />
            {backendOnline ? 'Backend Online' : 'Backend Offline'}
          </div>
          {error && (
            <div className="flex items-center gap-1 text-xs text-red-400">
              <AlertCircle size={13} />
              Error
            </div>
          )}
        </div>
      </header>

      {/* ── Pages ─────────────────────────────────────────────────────────── */}
      {page === 'simulator' && (
        <div className="flex flex-1 overflow-hidden">
          {/* Left sidebar: controls */}
          <aside className="w-72 shrink-0 border-r border-slate-700 flex flex-col overflow-hidden">
            <ControlPanel />
          </aside>

          {/* Center + right: graph + dashboard */}
          <div ref={containerRef} className="flex-1 flex flex-col overflow-hidden min-w-0">
            {/* Network graph — fills remaining space */}
            <div className="flex-1 overflow-hidden min-h-0">
              <NetworkGraph />
            </div>

            {/* Drag handle */}
            <DragHandle direction="vertical" onResize={handleResize} />

            {/* Results dashboard — resizable */}
            <div
              className="overflow-hidden shrink-0"
              style={{ height: bottomHeight ?? '40%' }}
            >
              <ResultsDashboard />
            </div>
          </div>

          {/* Right panel: collapsible AI Analysis */}
          <AIAnalysisPanel />
        </div>
      )}

      {page === 'pump-monitoring' && (
        <div className="flex-1 overflow-hidden">
          <PumpMonitoringDashboard onBack={() => setPage('simulator')} />
        </div>
      )}
    </div>
  );
};

export default App;
