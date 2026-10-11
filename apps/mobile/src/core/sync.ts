// Cloud sync when connectivity returns: upload pending messages, then pull delivery/ack states (SRS 11.2 steps 6-7).
import type { Envelope } from './envelope.ts';
import type { MessageStore } from './store.ts';

export interface SyncApi {
  peerSync(msgs: Envelope[]): Promise<{ results: { message_id: string; status: 'accepted' | 'duplicate' | 'rejected' | 'rate_limited'; problems: string[] }[]; states: Record<string, string> }>;
  status(ids: string[]): Promise<Record<string, string>>;
}

export async function syncOnce(store: MessageStore, api: SyncApi, now: Date): Promise<{ uploaded: number; rejected: number; acknowledged: number }> {
  store.purge(now);
  let uploaded = 0, rejected = 0, acknowledged = 0;
  const pending = store.pendingUpload().slice(0, 50);
  if (pending.length) {
    const r = await api.peerSync(pending);                       // throws on network error -> nothing marked, retried later
    for (const res of r.results) {
      if (res.status === 'rate_limited') continue;               // transient: keep pending and retry on the next sync
      store.markUploaded([res.message_id]);                      // rejected messages are permanent failures: do not retry forever
      if (res.status === 'rejected') { rejected++; continue; }
      uploaded++; store.advance(res.message_id, 'delivered');
    }
  }
  const mine = store.own().filter((x) => x.state !== 'acknowledged').map((x) => x.envelope.message_id);
  if (mine.length) {
    const states = await api.status(mine.slice(0, 100));
    for (const [id, s] of Object.entries(states)) {
      if (s === 'acknowledged' || s === 'resolved') { if (store.advance(id, 'acknowledged')) acknowledged++; }
      else if (s === 'received') store.advance(id, 'delivered');
    }
  }
  return { uploaded, rejected, acknowledged };
}
