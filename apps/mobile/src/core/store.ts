// Outbox / inbox with dedup, expiry and a forward-only delivery state machine (SRS 11.2, FR-11/12).
import type { Envelope } from './envelope.ts';

export type DeliveryState = 'queued' | 'relayed' | 'delivered' | 'acknowledged' | 'received';
const ORDER: DeliveryState[] = ['queued', 'relayed', 'delivered', 'acknowledged'];
export interface Rec { envelope: Envelope; origin: 'self' | 'peer'; state: DeliveryState; addedAt: number; relayCount: number; uploaded: boolean }
export interface Persist { load(): Promise<Rec[]>; save(rows: Rec[]): Promise<void> }

export class MessageStore {
  private rows = new Map<string, Rec>();
  private persist: Persist | null;
  constructor(persist: Persist | null = null) { this.persist = persist; }

  async hydrate(now: Date): Promise<void> {
    if (!this.persist) return;
    for (const r of await this.persist.load()) this.rows.set(r.envelope.message_id, r);
    this.purge(now);
  }
  private async flush(): Promise<void> { if (this.persist) await this.persist.save([...this.rows.values()]); }

  add(e: Envelope, origin: 'self' | 'peer', now: Date): 'added' | 'duplicate' | 'expired' {
    if (now.getTime() >= Date.parse(e.expires_at)) return 'expired';
    const ex = this.rows.get(e.message_id);
    if (ex) {                                             // hop_count is unsigned: keep the LOWEST seen so a forged high count can't stop relaying
      if (e.hop_count < ex.envelope.hop_count) { ex.envelope = { ...ex.envelope, hop_count: e.hop_count }; void this.flush(); }
      return 'duplicate';
    }
    this.rows.set(e.message_id, { envelope: e, origin, state: origin === 'self' ? 'queued' : 'received', addedAt: now.getTime(), relayCount: 0, uploaded: false });
    void this.flush();
    return 'added';
  }
  purge(now: Date): number {
    let n = 0;
    for (const [id, r] of this.rows) if (now.getTime() >= Date.parse(r.envelope.expires_at)) { this.rows.delete(id); n++; }
    if (n) void this.flush();
    return n;
  }
  get(id: string): Rec | undefined { return this.rows.get(id); }
  all(): Rec[] { return [...this.rows.values()]; }
  own(): Rec[] { return this.all().filter((r) => r.origin === 'self'); }
  ids(): string[] { return [...this.rows.keys()]; }
  count(): number { return this.rows.size; }

  /** Envelopes eligible to forward: unexpired and below the hop limit. */
  relayable(now: Date): Envelope[] {
    return this.all().map((r) => r.envelope).filter((e) => now.getTime() < Date.parse(e.expires_at) && e.hop_count < e.max_hops);
  }
  /** Forward-only transitions; a late 'relayed' never overwrites 'delivered'. */
  advance(id: string, to: DeliveryState): boolean {
    const r = this.rows.get(id);
    if (!r || r.origin !== 'self') return false;
    if (ORDER.indexOf(to) <= ORDER.indexOf(r.state)) return false;
    r.state = to; void this.flush(); return true;
  }
  noteRelayed(id: string): void { const r = this.rows.get(id); if (r) { r.relayCount++; this.advance(id, 'relayed'); } }
  /** Anything not yet confirmed to the backend; a gateway/online device uploads these. */
  pendingUpload(): Envelope[] { return this.all().filter((r) => r.state !== 'delivered' && r.state !== 'acknowledged' && !r.uploaded).map((r) => r.envelope); }
  markUploaded(ids: string[]): void { for (const id of ids) { const r = this.rows.get(id); if (r) r.uploaded = true; } }
}
