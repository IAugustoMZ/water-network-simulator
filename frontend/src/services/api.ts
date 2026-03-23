import axios from 'axios';
import type { SimulationResult, SimulationPreview, ScenarioOverrides, PumpCurveData, AIAnalysisResult } from '../types/network';

const BASE_URL = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
});

export const api = {
  getDefaultNetworkId: async (): Promise<string> => {
    const res = await client.get('/network/default-id');
    return res.data.network_id;
  },

  listScenarios: async (): Promise<Record<string, { description: string }>> => {
    const res = await client.get('/scenarios');
    return res.data;
  },

  runSimulation: async (params: {
    network_id: string;
    scenario_name?: string;
    overrides?: Partial<ScenarioOverrides>;
  }): Promise<SimulationPreview> => {
    const res = await client.post('/simulate', {
      network_id: params.network_id,
      scenario_name: params.scenario_name || 'baseline',
      overrides: {
        pumps: {},
        valves: {},
        demand_multipliers: {},
        global_demand_multiplier: 1.0,
        tank_levels: {},
        ...params.overrides,
      },
    });
    return res.data;
  },

  getResults: async (resultId: string): Promise<SimulationResult> => {
    const res = await client.get(`/results/${resultId}`);
    return res.data;
  },

  health: async (): Promise<{ status: string }> => {
    const res = await client.get('/health');
    return res.data;
  },

  getPumpCurves: async (networkId: string): Promise<PumpCurveData[]> => {
    const res = await client.get(`/network/${networkId}/pump-curves`);
    return res.data;
  },

  analyzeSimulation: async (resultId: string): Promise<AIAnalysisResult> => {
    const res = await client.post(`/analyze/${resultId}`);
    return res.data;
  },
};
