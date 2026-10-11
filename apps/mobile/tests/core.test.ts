import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { b64ToBytes, bytesToB64 } from '../src/core/b64.ts';
import { createEnvelope, decodePayload, signingString, validate, type Envelope } from '../src/core/envelope.ts';
import { MessageStore } from '../src/core/store.ts';
import { planSend, receive, simulateEncounter } from '../src/core/relay.ts';
import { displayStatus } from '../src/core/cache.ts';
import { STRINGS, t } from '../src/core/i18n.ts';
import { newNodeCrypto, nodeCryptoFromSeed, nodeVerify } from './nodeCrypto.ts';

const NOW = new Date('2024-09-28T12:00:00Z');
const later = (h: number) => new Date(NOW.getTime() + h * 3600 * 1000);
const mk = (c = newNodeCrypto(), over: any = {}) =>
  createEnvelope(c, { type: 'SOS', latE4: 261500, lonE4: 859000, severity: 3, payload: { people_count: 2, medical: false, note: 'छत' }, now: NOW, ...over });
const V = nodeVerify;

test('cross-language: Python-signed vector verifies in TS and TS reproduces the identical signature', () => {
  const v = JSON.parse(readFileSync(new URL('../../../data/fixtures/envelope_vector.json', import.meta.url), 'utf8'));
  const e: Envelope = v.envelope;
  assert.equal(signingString(e), v.signing_string);                       // canonical string identical byte-for-byte
  assert.deepEqual(validate(e, new Date(v.now), { verify: V }), []);       // Python signature verifies here
  const c = nodeCryptoFromSeed(Buffer.from(v.TEST_ONLY_seed_hex, 'hex'));
  assert.equal(c.sign(new TextEncoder().encode(v.signing_string)), e.signature);   // Ed25519 is deterministic
  assert.equal(decodePayload(e).note, 'छत पर / on roof');                 // UTF-8 survives
});

test('base64 round trip and strictness', () => {
  for (const s of ['', 'a', 'ab', 'abc', 'abcd', 'छत']) {
    const b = new TextEncoder().encode(s);
    assert.equal(bytesToB64(b), Buffer.from(b).toString('base64'));
    assert.deepEqual([...b64ToBytes(bytesToB64(b))], [...b]);
  }
  assert.throws(() => b64ToBytes('@@@@'));
});

test('envelope validation: ok, tamper, expiry, hops, ttl, malformed; hop_count is not signed', () => {
  const e = mk();
  assert.deepEqual(validate(e, NOW, { verify: V }), []);
  assert.deepEqual(validate({ ...e, hop_count: 3 }, NOW, { verify: V }), []);
  assert.deepEqual(validate({ ...e, lat_e4: e.lat_e4 + 1 }, NOW, { verify: V }), ['bad_signature']);
  assert.ok(validate(e, later(25), { verify: V }).includes('expired'));
  assert.ok(validate({ ...e, hop_count: 6 }, NOW, { verify: V }).includes('bad_hops'));
  assert.ok(validate(mk(undefined, { ttlHours: 100 }), NOW, { verify: V }).includes('bad_ttl'));
  assert.deepEqual(validate({ x: 1 }, NOW, { verify: V }), ['malformed']);
  assert.deepEqual(validate(null, NOW, { verify: V }), ['malformed']);
});

test('store: dedup, expiry purge, forward-only delivery states', () => {
  const s = new MessageStore(), e = mk();
  assert.equal(s.add(e, 'self', NOW), 'added');
  assert.equal(s.add(e, 'self', NOW), 'duplicate');
  assert.equal(s.get(e.message_id)!.state, 'queued');
  assert.ok(s.advance(e.message_id, 'delivered'));
  assert.equal(s.advance(e.message_id, 'relayed'), false);                 // no regression
  assert.ok(s.advance(e.message_id, 'acknowledged'));
  assert.equal(s.add(mk(undefined, { ttlHours: 1 }), 'peer', later(2)), 'expired');
  assert.equal(s.purge(later(25)), 1);
  assert.equal(s.count(), 0);
});

test('relay chain A -> B -> C increments hops, stops at max_hops, and never relays expired/forged messages', () => {
  const c = newNodeCrypto(), A = new MessageStore(), B = new MessageStore(), C = new MessageStore();
  const e = mk(c, { maxHops: 2 });
  A.add(e, 'self', NOW);
  simulateEncounter(A, B, { verify: V }, NOW);
  assert.equal(B.get(e.message_id)!.envelope.hop_count, 1);
  assert.equal(A.get(e.message_id)!.state, 'relayed');                     // origin sees "relayed"
  simulateEncounter(B, C, { verify: V }, NOW);
  assert.equal(C.get(e.message_id)!.envelope.hop_count, 2);
  const D = new MessageStore();
  simulateEncounter(C, D, { verify: V }, NOW);                             // hop 2 == max_hops: must not go further
  assert.equal(D.count(), 0);
  const E = new MessageStore();
  simulateEncounter(A, E, { verify: V }, later(25));                       // expired
  assert.equal(E.count(), 0);
  const forged = { ...mk(c), severity: 1 as const };                       // tampered after signing
  const r = receive(new MessageStore(), [forged], { verify: V }, NOW);
  assert.deepEqual(r[0].problems, ['bad_signature']);
});

test('deduplication: a message arriving over two paths is stored and uploaded once at the sink', () => {
  const c = newNodeCrypto(), A = new MessageStore(), B = new MessageStore(), SINK = new MessageStore();
  const e = mk(c); A.add(e, 'self', NOW);
  simulateEncounter(A, B, { verify: V }, NOW);
  simulateEncounter(A, SINK, { verify: V }, NOW);                          // path 1
  simulateEncounter(B, SINK, { verify: V }, NOW);                          // path 2 (duplicate)
  assert.equal(SINK.count(), 1);
  assert.equal(SINK.pendingUpload().length, 1);
  SINK.markUploaded([e.message_id]);
  assert.equal(SINK.pendingUpload().length, 0);
  assert.equal(planSend(SINK, [e.message_id], NOW).length, 0);             // peer already has it: nothing re-sent
});

test('offline status is never "live" without network or when overdue', () => {
  const live = { response: { live: true, expired: false, state: 'WATCH' }, fetchedAt: NOW.getTime() };
  assert.equal(displayStatus(live, NOW.getTime() + 60_000, true).mode, 'live');
  assert.equal(displayStatus(live, NOW.getTime() + 60_000, false).mode, 'cached');
  assert.equal(displayStatus(live, NOW.getTime() + 2 * 3600_000, true).mode, 'cached');
  assert.equal(displayStatus(live, NOW.getTime() + 7 * 3600_000, true).mode, 'expired');
  assert.equal(displayStatus(null, NOW.getTime(), true).mode, 'none');
});

test('i18n: en/hi key parity, placeholders preserved, no overconfident wording', () => {
  const en = Object.keys(STRINGS.en).sort(), hi = Object.keys(STRINGS.hi).sort();
  assert.deepEqual(en, hi);
  for (const k of en) {
    const ph = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
    assert.equal(ph((STRINGS.en as any)[k]), ph((STRINGS.hi as any)[k]), k);
    assert.ok((STRINGS.hi as any)[k].length > 0);
  }
  for (const s of Object.values(STRINGS.en)) assert.doesNotMatch(s, /guarantee|will flood|\d+\s?%/i);
  assert.equal(t('hi', 'updated.minutes', { n: 11 }), '11 मिनट पहले अपडेट हुआ');
  assert.notEqual(t('hi', 'state.EVACUATE'), t('en', 'state.EVACUATE'));
});

import { syncOnce, type SyncApi } from '../src/core/sync.ts';
test('sync: uploads once, marks delivered, picks up responder ack, survives network failure, drops rejects', async () => {
  const c = newNodeCrypto(), S = new MessageStore(), e = mk(c), foreign = mk();
  S.add(e, 'self', NOW); S.add(foreign, 'peer', NOW);
  const server = new Map<string, string>();
  const api: SyncApi & { down: boolean } = {
    down: true,
    async peerSync(msgs) { if (this.down) throw new Error('offline'); msgs.forEach((m) => server.set(m.message_id, 'received'));
      return { results: msgs.map((m) => ({ message_id: m.message_id, status: 'accepted' as const, problems: [] })), states: {} }; },
    async status(ids) { return Object.fromEntries(ids.filter((i) => server.has(i)).map((i) => [i, server.get(i)!])); },
  };
  await assert.rejects(syncOnce(S, api, NOW));                              // offline: nothing lost
  assert.equal(S.pendingUpload().length, 2);
  api.down = false;
  assert.equal((await syncOnce(S, api, NOW)).uploaded, 2);
  assert.equal(S.get(e.message_id)!.state, 'delivered');
  assert.equal(S.pendingUpload().length, 0);
  server.set(e.message_id, 'acknowledged');                                  // responder acknowledges on the dashboard
  assert.equal((await syncOnce(S, api, NOW)).acknowledged, 1);
  assert.equal(S.get(e.message_id)!.state, 'acknowledged');
});

import { payloadProblems } from '../src/core/envelope.ts';
test('payload schema (parity with Python): unknown keys, wrong types, oversize note, bad report type', () => {
  const enc = (o: unknown) => bytesToB64(new TextEncoder().encode(JSON.stringify(o)));
  assert.deepEqual(payloadProblems('SOS', enc({ people_count: 3, medical: true, note: 'छत' })), []);
  for (const bad of [{ people_count: -1 }, { people_count: 501 }, { people_count: '3' }, { medical: 1 }, { note: 'x'.repeat(141) }, { evil: 1 }, [1]])
    assert.deepEqual(payloadProblems('SOS', enc(bad)), ['bad_payload'], JSON.stringify(bad));
  assert.deepEqual(payloadProblems('REPORT', enc({ type: 'blocked_road', value: 1.5 })), []);
  assert.deepEqual(payloadProblems('REPORT', enc({ type: 'nope' })), ['bad_payload']);
  assert.deepEqual(payloadProblems('SOS', bytesToB64(new TextEncoder().encode('not json'))), ['bad_payload']);
  const e = mk(undefined, { payload: { people_count: 'many' } });          // validly signed but schema-invalid
  assert.deepEqual(validate(e, NOW, { verify: V }), ['bad_payload']);
});

test('sync: rate_limited stays pending (retried later); rejected is dropped permanently', async () => {
  const S = new MessageStore(), a = mk(), b = mk(); S.add(a, 'self', NOW); S.add(b, 'self', NOW);
  const api = { async peerSync(m: any[]) { return { results: [{ message_id: a.message_id, status: 'rate_limited' as const, problems: ['peer_quota'] }, { message_id: b.message_id, status: 'rejected' as const, problems: ['bad_signature'] }], states: {} }; }, async status() { return {}; } };
  await syncOnce(S, api as any, NOW);
  assert.deepEqual(S.pendingUpload().map((e) => e.message_id), [a.message_id]);
});

test('hop_count is unsigned: a forged high copy arriving first cannot stop relaying once an honest lower copy arrives', () => {
  const c = newNodeCrypto(), S = new MessageStore(), e = mk(c, { maxHops: 3 });
  assert.equal(S.add({ ...e, hop_count: 3 }, 'peer', NOW), 'added');           // malicious relay's copy: already at the limit
  assert.equal(S.relayable(NOW).length, 0);
  assert.equal(S.add({ ...e, hop_count: 1 }, 'peer', NOW), 'duplicate');       // honest copy
  assert.equal(S.get(e.message_id)!.envelope.hop_count, 1);
  assert.equal(S.relayable(NOW).length, 1);
  S.add({ ...e, hop_count: 3 }, 'peer', NOW);                                  // never raised again
  assert.equal(S.get(e.message_id)!.envelope.hop_count, 1);
  assert.deepEqual(validate(S.get(e.message_id)!.envelope, NOW, { verify: V }), []);   // signature still valid
});
