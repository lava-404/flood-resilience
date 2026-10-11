// Honest status wording: never "live" while offline or when the forecast is overdue (SRS 8.5, FR-10).
export interface CachedRisk { response: { live: boolean; expired: boolean; state: string }; fetchedAt: number }
export type Mode = 'live' | 'cached' | 'expired' | 'none';
const STALE_MS = 90 * 60 * 1000, EXPIRED_MS = 6 * 3600 * 1000;

export function displayStatus(cache: CachedRisk | null, nowMs: number, online: boolean): { mode: Mode; ageMinutes: number | null } {
  if (!cache) return { mode: 'none', ageMinutes: null };
  const age = nowMs - cache.fetchedAt;
  const ageMinutes = Math.max(0, Math.floor(age / 60000));
  if (cache.response.expired || age > EXPIRED_MS) return { mode: 'expired', ageMinutes };
  if (online && cache.response.live && age <= STALE_MS) return { mode: 'live', ageMinutes };
  return { mode: 'cached', ageMinutes };
}
