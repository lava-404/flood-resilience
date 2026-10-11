// Store-and-forward relay logic, independent of the transport (Wi-Fi Direct / LAN / BLE).
import { validate, type CryptoPort, type Envelope } from './envelope.ts';
import type { MessageStore } from './store.ts';

/** What to send to a peer who told us which ids it already has. Hop count is incremented on the wire. */
export function planSend(local: MessageStore, remoteIds: string[], now: Date): Envelope[] {
  const have = new Set(remoteIds);
  return local.relayable(now).filter((e) => !have.has(e.message_id)).map((e) => ({ ...e, hop_count: e.hop_count + 1 }));
}

export interface ReceiveResult { id: string; status: 'added' | 'duplicate' | 'rejected'; problems: string[] }

/** Verify, then dedup into the local store. Invalid/expired/over-hop/forged messages are dropped, never relayed. */
export function receive(local: MessageStore, incoming: unknown[], c: Pick<CryptoPort, 'verify'>, now: Date): ReceiveResult[] {
  return incoming.map((raw: any) => {
    const problems = validate(raw, now, c);
    if (problems.length) return { id: String(raw?.message_id ?? '?'), status: 'rejected' as const, problems };
    const r = local.add(raw as Envelope, 'peer', now);
    return { id: raw.message_id, status: r === 'added' ? ('added' as const) : ('duplicate' as const), problems: [] };
  });
}

/** In-process simulation of two devices meeting (used by tests; NOT a substitute for a real-device test). */
export function simulateEncounter(a: MessageStore, b: MessageStore, c: Pick<CryptoPort, 'verify'>, now: Date): void {
  const toB = planSend(a, b.ids(), now), toA = planSend(b, a.ids(), now);
  receive(b, toB, c, now); receive(a, toA, c, now);
  for (const e of toB) a.noteRelayed(e.message_id);
  for (const e of toA) b.noteRelayed(e.message_id);
}
