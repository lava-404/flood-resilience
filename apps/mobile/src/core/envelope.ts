// Signed message envelope v1. Contract shared with Python: docs/data-contracts/envelope.md
import { b64ToBytes, bytesToB64, fromUtf8, utf8 } from './b64.ts';

export const PROTOCOL_VERSION = 1;
export const MAX_HOPS_LIMIT = 8;
export const MAX_TTL_MS = 72 * 3600 * 1000;
export const MAX_PAYLOAD_BYTES = 2048;

export interface Envelope {
  protocol_version: number; message_id: string; origin_peer_id: string; message_type: 'SOS' | 'REPORT';
  created_at: string; expires_at: string; hop_count: number; max_hops: number;
  lat_e4: number; lon_e4: number; severity: 1 | 2 | 3; payload_b64: string; signature: string;
}
export interface CryptoPort {
  publicKeyHex: string;
  sign(msg: Uint8Array): string;                                   // Ed25519 -> hex signature
  verify(pubHex: string, msg: Uint8Array, sigHex: string): boolean;
  randomId(): string;
}

export const isoSeconds = (d: Date): string => d.toISOString().replace(/\.\d{3}Z$/, 'Z');

export function signingString(e: Omit<Envelope, 'signature' | 'hop_count'>): string {
  return ['FR1', e.protocol_version, e.message_id, e.origin_peer_id, e.message_type, e.created_at, e.expires_at,
    e.max_hops, e.lat_e4, e.lon_e4, e.severity, e.payload_b64].join('\n');   // hop_count deliberately NOT signed
}

export interface NewMessage { type: 'SOS' | 'REPORT'; latE4: number; lonE4: number; severity: 1 | 2 | 3; payload: object; now: Date; ttlHours?: number; maxHops?: number }

export function createEnvelope(c: CryptoPort, m: NewMessage): Envelope {
  const base = {
    protocol_version: PROTOCOL_VERSION, message_id: c.randomId(), origin_peer_id: c.publicKeyHex, message_type: m.type,
    created_at: isoSeconds(m.now), expires_at: isoSeconds(new Date(m.now.getTime() + (m.ttlHours ?? 24) * 3600 * 1000)),
    max_hops: m.maxHops ?? 5, lat_e4: m.latE4, lon_e4: m.lonE4, severity: m.severity,
    payload_b64: bytesToB64(utf8(JSON.stringify(m.payload))),
  };
  return { ...base, hop_count: 0, signature: c.sign(utf8(signingString(base))) };
}

/** Returns problem codes ([] = acceptable). Same codes as services/common/floodcommon/envelope.py. */
export function validate(e: any, now: Date, c: Pick<CryptoPort, 'verify'> | null): string[] {
  try {
    if (typeof e !== 'object' || e === null) return ['malformed'];
    const p: string[] = [];
    const ints = ['protocol_version', 'hop_count', 'max_hops', 'lat_e4', 'lon_e4', 'severity'];
    if (!ints.every((k) => Number.isInteger(e[k]))) return ['malformed'];
    for (const k of ['message_id', 'origin_peer_id', 'message_type', 'created_at', 'expires_at', 'payload_b64', 'signature'])
      if (typeof e[k] !== 'string') return ['malformed'];
    const cr = Date.parse(e.created_at), ex = Date.parse(e.expires_at);
    if (Number.isNaN(cr) || Number.isNaN(ex)) return ['malformed'];
    if (e.protocol_version !== PROTOCOL_VERSION) p.push('bad_protocol_version');
    if (e.message_type !== 'SOS' && e.message_type !== 'REPORT') p.push('bad_type');
    if (!/^[0-9a-f]{64}$/.test(e.origin_peer_id)) p.push('bad_peer_id');
    if (!(e.message_id.length > 0 && e.message_id.length <= 64)) p.push('bad_message_id');
    if (ex <= cr || ex - cr > MAX_TTL_MS) p.push('bad_ttl');
    if (now.getTime() >= ex) p.push('expired');
    if (cr > now.getTime() + 10 * 60 * 1000) p.push('created_in_future');
    if (!(e.hop_count >= 0 && e.hop_count <= e.max_hops && e.max_hops <= MAX_HOPS_LIMIT)) p.push('bad_hops');
    if (!(Math.abs(e.lat_e4) <= 900000 && Math.abs(e.lon_e4) <= 1800000)) p.push('bad_location');
    if (b64ToBytes(e.payload_b64).length > MAX_PAYLOAD_BYTES) p.push('payload_too_large');
    if (![1, 2, 3].includes(e.severity)) p.push('bad_severity');
    if ((e.message_type === 'SOS' || e.message_type === 'REPORT') && !p.includes('payload_too_large')) p.push(...payloadProblems(e.message_type, e.payload_b64));
    if (p.length === 0 && c && !c.verify(e.origin_peer_id, utf8(signingString(e)), e.signature)) p.push('bad_signature');
    return p;
  } catch {
    return ['malformed'];
  }
}

const REPORT_TYPES = ['water_depth', 'blocked_road', 'stranded_person', 'bridge_structure'];
/** Strict payload schema; mirrors floodcommon.envelope.payload_problems (unknown keys rejected). */
export function payloadProblems(type: string, b64: string): string[] {
  let p: any;
  try { p = JSON.parse(fromUtf8(b64ToBytes(b64))); } catch { return ['bad_payload']; }
  if (typeof p !== 'object' || p === null || Array.isArray(p)) return ['bad_payload'];
  const allowed = type === 'SOS' ? ['people_count', 'medical', 'note'] : ['type', 'value', 'note'];
  if (Object.keys(p).some((k) => !allowed.includes(k))) return ['bad_payload'];
  if (p.note != null && (typeof p.note !== 'string' || [...p.note].length > 140)) return ['bad_payload'];
  if (type === 'SOS') {
    if (p.people_count != null && !(Number.isInteger(p.people_count) && p.people_count >= 0 && p.people_count <= 500)) return ['bad_payload'];
    if (p.medical != null && typeof p.medical !== 'boolean') return ['bad_payload'];
  } else {
    if (!REPORT_TYPES.includes(p.type)) return ['bad_payload'];
    if (p.value != null && !(typeof p.value === 'number' && Number.isFinite(p.value) && Math.abs(p.value) <= 1000)) return ['bad_payload'];
  }
  return [];
}

export const decodePayload = (e: Envelope): any => JSON.parse(fromUtf8(b64ToBytes(e.payload_b64)));
