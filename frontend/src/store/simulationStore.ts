import { create } from 'zustand';
import type { SimulationResult, ScenarioOverrides } from '../types/network';
import { api } from '../services/api';

export const SCENARIO_LABELS: Record<string, string> = {
  baseline: 'Baseline Operation',
  valve_restriction: 'Valve Restriction',
  pump_speed_reduction: 'Pump Speed Reduction (80%)',
  pump_failure: 'Pump Failure (PUMP1 Off)',
  demand_increase: 'Peak Demand (+20%)',
  high_elevation_stress: 'High-Elevation Stress',
};

export const SCENARIOS = Object.keys(SCENARIO_LABELS);

const DEFAULT_OVERRIDES: ScenarioOverrides = {
  pumps: {},
  valves: {},
  demand_multipliers: {},
  global_demand_multiplier: 1.0,
  tank_levels: {},
};

interface SimulationState {
  networkId: string | null;
  currentScenario: string;
  overrides: ScenarioOverrides;
  resultId: string | null;
  result: SimulationResult | null;
  isLoading: boolean;
  error: string | null;
  backendOnline: boolean;

  initialize: () => Promise<void>;
  setScenario: (scenario: string) => void;
  setPumpOn: (pumpId: string, isOn: boolean) => void;
  setPumpSpeed: (pumpId: string, speedRatio: number) => void;
  setValveOpening: (valveId: string, opening: number) => void;
  setGlobalDemandMultiplier: (multiplier: number) => void;
  runSimulation: () => Promise<void>;
  resetOverrides: () => void;
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  networkId: null,
  currentScenario: 'baseline',
  overrides: { ...DEFAULT_OVERRIDES },
  resultId: null,
  result: null,
  isLoading: false,
  error: null,
  backendOnline: false,

  initialize: async () => {
    try {
      const networkId = await api.getDefaultNetworkId();
      set({ networkId, backendOnline: true, error: null });
    } catch {
      set({ error: 'Cannot connect to backend. Is it running?', backendOnline: false });
    }
  },

  setScenario: (scenario) => {
    set({ currentScenario: scenario, overrides: { ...DEFAULT_OVERRIDES } });
  },

  setPumpOn: (pumpId, isOn) => {
    set((state) => ({
      overrides: {
        ...state.overrides,
        pumps: {
          ...state.overrides.pumps,
          [pumpId]: { ...state.overrides.pumps[pumpId], is_on: isOn },
        },
      },
    }));
  },

  setPumpSpeed: (pumpId, speedRatio) => {
    set((state) => ({
      overrides: {
        ...state.overrides,
        pumps: {
          ...state.overrides.pumps,
          [pumpId]: { ...state.overrides.pumps[pumpId], speed_ratio: speedRatio },
        },
      },
    }));
  },

  setValveOpening: (valveId, opening) => {
    set((state) => ({
      overrides: {
        ...state.overrides,
        valves: {
          ...state.overrides.valves,
          [valveId]: { ...state.overrides.valves[valveId], opening_fraction: opening },
        },
      },
    }));
  },

  setGlobalDemandMultiplier: (multiplier) => {
    set((state) => ({
      overrides: { ...state.overrides, global_demand_multiplier: multiplier },
    }));
  },

  runSimulation: async () => {
    const { networkId, currentScenario, overrides } = get();
    if (!networkId) {
      set({ error: 'No network loaded. Check backend connection.' });
      return;
    }
    set({ isLoading: true, error: null });
    try {
      const preview = await api.runSimulation({
        network_id: networkId,
        scenario_name: currentScenario,
        overrides,
      });
      const fullResult = await api.getResults(preview.result_id);
      set({ result: fullResult, resultId: preview.result_id, isLoading: false });
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string; message?: string } } })
          ?.response?.data?.detail ||
        (e as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        (e as Error)?.message ||
        'Simulation failed';
      set({ error: typeof msg === 'string' ? msg : JSON.stringify(msg), isLoading: false });
    }
  },

  resetOverrides: () => {
    set({ overrides: { ...DEFAULT_OVERRIDES } });
  },
}));
