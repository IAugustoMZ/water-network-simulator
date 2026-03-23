import React, { useState } from 'react';
import { Sparkles, Loader2, X } from 'lucide-react';
import { useSimulationStore } from '../../store/simulationStore';
import type { AIAnalysisResult } from '../../types/network';
import { api } from '../../services/api';

const AIAnalysisPanel: React.FC = () => {
  const result = useSimulationStore((s) => s.result);
  const [open, setOpen] = useState(false);
  const [analysis, setAnalysis] = useState<AIAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAnalysis = async () => {
    if (!result?.result_id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.analyzeSimulation(result.result_id);
      setAnalysis(data);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } }; message?: string });
      setError(detail?.response?.data?.detail ?? detail?.message ?? 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const severityStyle: Record<string, string> = {
    critical: 'bg-red-900/40 border-red-700 text-red-300',
    warning: 'bg-yellow-900/40 border-yellow-700 text-yellow-300',
    info: 'bg-blue-900/40 border-blue-700 text-blue-300',
  };
  const priorityBadge: Record<number, string> = {
    1: 'bg-red-700 text-red-100',
    2: 'bg-amber-700 text-amber-100',
    3: 'bg-slate-600 text-slate-200',
  };
  const healthColor = (s: number) =>
    s >= 70 ? 'text-green-400' : s >= 40 ? 'text-amber-400' : 'text-red-400';

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex flex-col items-center justify-center flex-1 gap-3 text-slate-400">
          <Loader2 size={28} className="animate-spin text-purple-400" />
          <span className="text-xs text-center">Analyzing with AI…<br />this may take 10–20 s</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className="space-y-3 p-3">
          <div className="bg-red-900/30 border border-red-600 rounded p-3 text-xs text-red-300">
            <strong>Analysis failed:</strong> {error}
            {error.includes('GROQ_API_KEY') && (
              <p className="mt-1">Set GROQ_API_KEY in your .env file and restart the backend.</p>
            )}
          </div>
          <button
            onClick={runAnalysis}
            className="px-4 py-2 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors"
          >
            Retry
          </button>
        </div>
      );
    }

    if (!analysis) {
      return (
        <div className="flex flex-col items-center justify-center flex-1 gap-4 p-4">
          <Sparkles size={36} className="text-purple-400" />
          <p className="text-xs text-slate-400 text-center leading-relaxed">
            Get AI-powered hydraulic analysis and actionable recommendations from your simulation results.
          </p>
          <button
            onClick={runAnalysis}
            disabled={!result}
            className="flex items-center gap-2 px-4 py-2.5 bg-purple-700 hover:bg-purple-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-xs font-semibold transition-colors"
          >
            <Sparkles size={13} /> Analyze with AI
          </button>
        </div>
      );
    }

    return (
      <div className="space-y-4 p-3">
        {/* Health Score */}
        <div className="flex items-center gap-3 bg-slate-700 rounded-lg p-3">
          <div className="text-center shrink-0">
            <div className={`text-4xl font-bold tabular-nums ${healthColor(analysis.health_score)}`}>
              {analysis.health_score}
            </div>
            <div className="text-[9px] text-slate-400 uppercase tracking-wider">Health</div>
          </div>
          <p className="text-xs text-slate-200 leading-relaxed">{analysis.summary}</p>
        </div>

        {/* Issues */}
        {analysis.issues.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
              Issues ({analysis.issues.length})
            </div>
            <div className="space-y-1.5">
              {analysis.issues.map((iss, i) => (
                <div
                  key={i}
                  className={`border rounded px-2.5 py-2 text-xs ${severityStyle[iss.severity] ?? 'bg-slate-700 border-slate-600 text-slate-300'}`}
                >
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="font-semibold uppercase text-[9px] tracking-wider">
                      {iss.severity} · {iss.category}
                    </span>
                    {iss.component_id && (
                      <span className="font-mono bg-black/20 px-1.5 rounded text-[9px]">
                        {iss.component_id}
                      </span>
                    )}
                  </div>
                  <div>{iss.description}</div>
                  {iss.metric && <div className="mt-0.5 opacity-75">Metric: {iss.metric}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Overall strategy */}
        <div className="bg-purple-900/30 border border-purple-700 rounded p-2.5 text-xs text-purple-200">
          <div className="font-semibold uppercase tracking-wide text-purple-400 mb-1 text-[10px]">
            Operational Strategy
          </div>
          {analysis.overall_strategy}
        </div>

        {/* Recommendations */}
        {analysis.recommendations.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
              Recommendations ({analysis.recommendations.length})
            </div>
            <div className="space-y-2">
              {analysis.recommendations.map((rec, i) => (
                <div key={i} className="bg-slate-700 border border-slate-600 rounded p-2.5">
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="text-xs font-semibold text-slate-100">{rec.title}</span>
                    <div className="flex gap-1 shrink-0">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${priorityBadge[rec.priority] ?? 'bg-slate-600 text-slate-300'}`}
                      >
                        P{rec.priority}
                      </span>
                      {rec.component_id && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-blue-900/60 text-blue-300 font-mono">
                          {rec.component_id}
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-slate-300 mb-0.5">{rec.action}</p>
                  <p className="text-xs text-green-400">→ {rec.expected_impact}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Re-analyze */}
        <button
          onClick={runAnalysis}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-purple-400 transition-colors"
        >
          <Sparkles size={11} /> Re-analyze
        </button>
      </div>
    );
  };

  return (
    <aside
      className={`shrink-0 border-l border-slate-700 flex flex-col bg-slate-800 overflow-hidden transition-all duration-200 ${
        open ? 'w-80' : 'w-8'
      }`}
    >
      {!open ? (
        /* ── Collapsed strip ── */
        <button
          onClick={() => setOpen(true)}
          title="Open AI Analysis"
          className="flex-1 flex flex-col items-center justify-center gap-2 text-purple-400 hover:text-purple-300 hover:bg-slate-700/60 transition-colors"
        >
          <Sparkles size={15} />
          <span
            className="text-[9px] font-semibold uppercase tracking-widest text-purple-400"
            style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
          >
            AI Analysis
          </span>
        </button>
      ) : (
        /* ── Expanded panel ── */
        <>
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700 shrink-0 bg-slate-850">
            <div className="flex items-center gap-2 text-sm font-semibold text-purple-300">
              <Sparkles size={13} />
              AI Analysis
            </div>
            <button
              onClick={() => setOpen(false)}
              title="Close AI Analysis"
              className="text-slate-500 hover:text-slate-200 transition-colors"
            >
              <X size={14} />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto flex flex-col">{renderContent()}</div>
        </>
      )}
    </aside>
  );
};

export default AIAnalysisPanel;
