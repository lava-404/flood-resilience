import { API_BASE } from './config';
import type { Envelope } from './core/envelope.ts';

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 8000);
  try {
    const r = await fetch(API_BASE + path, { ...init, signal: ctl.signal, headers: { 'Content-Type': 'application/json' } });
    if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
    return (await r.json()) as T;
  } finally { clearTimeout(timer); }
}
const q = (o: Record<string, string | number>) => new URLSearchParams(Object.entries(o).map(([k, v]) => [k, String(v)])).toString();

export interface Risk { state: 'SAFE' | 'WATCH' | 'WARNING' | 'EVACUATE'; confidence: 'low' | 'medium' | 'high'; live: boolean; expired: boolean; age_minutes: number;
  generated_at: string; data_cutoff: string | null; model_version: string; forecast: Record<string, { q10: number; q50: number; q90: number }> | null;
  drivers: { name: string; value: number; unit: string; direction: string }[]; official: { status: string; source: string } | null;
  override: { message: string } | null; conflict: boolean; data_provenance?: string; station: { name: string; distance_km: number }; current_level_m?: number }

export const api = {
  risk: (lat: number, lon: number) => call<Risk>(`/v1/risk?${q({ lat, lon })}`),
  timeline: (lat: number, lon: number) => call<{ history: any[]; rainfall: any[] }>(`/v1/risk/timeline?${q({ lat, lon })}`),
  shelters: (lat: number, lon: number) => call<any[]>(`/v1/shelters/nearby?${q({ lat, lon })}`),
  reports: (lat: number, lon: number) => call<any[]>(`/v1/reports/nearby?${q({ lat, lon })}`),
  peerSync: (messages: Envelope[]) => call<any>('/v1/peer/sync', { method: 'POST', body: JSON.stringify({ messages }) }),
  status: (ids: string[]) => call<Record<string, string>>(`/v1/sos/status?ids=${ids.join(',')}`),
};
