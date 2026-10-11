// Pure view logic for the responder console (unit-tested under Node; no React, no network).
// Honesty rules: never say "live" unless the API says live && !expired; always label synthetic replay data; surface source problems.

export type ErrKind = 'auth' | 'locked' | 'not_configured' | 'network' | 'server';
export interface ApiError { status?: number; message: string }

export function classifyError(e: ApiError): { kind: ErrKind; title: string; hint: string } {
  switch (e.status) {
    case 401: return { kind: 'auth', title: 'Sign-in failed', hint: 'The responder token was not accepted.' };
    case 429: return { kind: 'locked', title: 'Too many attempts', hint: 'Locked for a few minutes. Wait, then try again.' };
    case 503: return { kind: 'not_configured', title: 'Responder access unavailable', hint: 'The server has no valid responder token configured, or its database is unreachable.' };
    case undefined: return { kind: 'network', title: 'Cannot reach the API', hint: 'Check the API address, your network and CORS settings. Data shown below (if any) is OUT OF DATE.' };
    default: return { kind: 'server', title: `Server error (${e.status})`, hint: e.message };
  }
}

export interface RiskRow {
  station: string; name: string; state?: string | null; confidence?: string; live?: boolean; expired?: boolean; age_minutes?: number;
  official?: { source: string; status: string; freshness?: string } | null; conflict?: boolean; override?: { message: string } | null; data_provenance?: string;
}
export type Tone = 'ok' | 'watch' | 'warn' | 'danger' | 'unknown';
const TONE: Record<string, Tone> = { SAFE: 'ok', WATCH: 'watch', WARNING: 'warn', EVACUATE: 'danger' };

export function riskBadge(r: RiskRow): { label: string; tone: Tone; caveats: string[] } {
  if (!r.state) return { label: 'NO FORECAST', tone: 'unknown', caveats: ['No forecast has been generated for this station.'] };
  const caveats: string[] = [];
  if (r.expired) caveats.push('EXPIRED: older than 6 h, not current.');
  else if (!r.live) caveats.push('NOT LIVE: data is stale, incomplete or the forecast is overdue.');
  if (r.confidence === 'low') caveats.push('Low confidence.');
  if (r.conflict) caveats.push('Model and official status disagree; the more cautious state is shown.');
  if (r.official?.freshness === 'stale') caveats.push('Official status is stale; the last known status is still applied.');
  if (r.override) caveats.push(r.override.message);
  return { label: r.state, tone: TONE[r.state] ?? 'unknown', caveats };
}

export interface SourceRow { source: string; state: string; last_success_at?: string | null; age_minutes?: number | null; last_status?: string; last_error?: string | null }
export function sourceProblems(h: SourceRow[] | undefined | null): { source: string; severity: 'error' | 'warn'; message: string }[] {
  if (!h || h.length === 0) return [{ source: '(none)', severity: 'error', message: 'No data sources have reported. There is no data to show.' }];
  return h.flatMap((s) => {
    if (s.state === 'ok') return [];
    if (s.state === 'never_succeeded') return [{ source: s.source, severity: 'error' as const, message: `No successful ingestion yet; no data from ${s.source}.${s.last_error ? ' ' + s.last_error : ''}` }];
    if (s.state === 'failing') return [{ source: s.source, severity: 'error' as const, message: `Latest run failed${s.last_error ? ': ' + s.last_error : ''}. Readings may be out of date.` }];
    return [{ source: s.source, severity: 'warn' as const, message: `Stale: last success ${formatAge(s.age_minutes)} ago.` }];
  });
}

export function dataBanner(o: { clock?: string; risks?: RiskRow[] } | null | undefined): { kind: 'synthetic' | 'none' | 'model'; text: string } {
  const rows = o?.risks ?? [];
  if (o?.clock === 'demo' || rows.some((r) => r.data_provenance === 'synthetic_reconstruction'))
    return { kind: 'synthetic', text: 'SYNTHETIC REPLAY: fictional station and made-up readings, shown on a pinned demo clock. These are not real flood measurements.' };
  if (rows.length === 0) return { kind: 'none', text: 'No stations are configured.' };
  return { kind: 'model', text: 'Model output only. Always cross-check official CWC/DHM warnings.' };
}

export function formatAge(min: number | null | undefined): string {
  if (min == null || !Number.isFinite(min)) return 'unknown time';
  if (min < 1) return 'under a minute';
  if (min < 90) return `${Math.round(min)} min`;
  if (min < 48 * 60) return `${Math.floor(min / 60)} h ${Math.round(min % 60)} min`;
  return `${Math.floor(min / 1440)} days`;
}

export interface Sos { message_id: string; lat: number; lon: number; people_count: number | null; medical_flag: boolean; state: string; hop_count: number }
/** ~0.05 degree (~5 km) grid cells: a simple, explainable grouping, not a statistical clustering model. */
export const cellOf = (lat: number, lon: number) => `${(Math.round(lat / 0.05) * 0.05).toFixed(2)}, ${(Math.round(lon / 0.05) * 0.05).toFixed(2)}`;
export function clusterSos(sos: Sos[]) {
  const m = new Map<string, Sos[]>();
  for (const s of sos) { const k = cellOf(s.lat, s.lon); m.set(k, [...(m.get(k) ?? []), s]); }
  return [...m.entries()].map(([cell, items]) => ({ cell, items, people: items.reduce((a, s) => a + (s.people_count ?? 0), 0), medical: items.filter((s) => s.medical_flag).length, unacknowledged: items.filter((s) => s.state === 'received').length }))
    .sort((a, b) => b.unacknowledged - a.unacknowledged || b.items.length - a.items.length);
}

export function refreshStatus(lastOkMs: number | null, nowMs: number, failing: boolean): { stale: boolean; text: string } {
  if (lastOkMs == null) return { stale: failing, text: failing ? 'No data loaded yet.' : 'Loading…' };
  const s = Math.max(0, Math.round((nowMs - lastOkMs) / 1000));
  return { stale: failing || s > 60, text: `${failing ? 'REFRESH FAILING. ' : ''}Last successful refresh ${s} s ago.` };
}
