import axios, { AxiosInstance } from 'axios';
import type {
  CorridorState,
  MetricsTick,
  OverrideCommand,
  PriorityWeights,
} from '../types';

const baseURL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ||
  'http://localhost:8000';

export const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function getState(): Promise<CorridorState> {
  const { data } = await apiClient.get<CorridorState>('/state');
  return data;
}

export async function getMetrics(params?: {
  from?: number;
  to?: number;
}): Promise<MetricsTick[]> {
  const { data } = await apiClient.get<MetricsTick[]>('/metrics', { params });
  return data;
}

export async function postOverride(cmd: OverrideCommand): Promise<void> {
  await apiClient.post('/override', cmd);
}

export async function postConfig(weights: Partial<PriorityWeights>): Promise<void> {
  await apiClient.post('/config', weights);
}

export const apiBaseUrl = baseURL;
