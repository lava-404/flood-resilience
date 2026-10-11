import { test } from 'node:test';
import assert from 'node:assert/strict';
import { classifyError, clusterSos, dataBanner, formatAge, refreshStatus, riskBadge, sourceProblems } from '../lib/view.ts';

test('error classification covers auth, lockout, unconfigured, network and server', () => {
  assert.equal(classifyError({ status: 401, message: '' }).kind, 'auth');
  assert.equal(classifyError({ status: 429, message: '' }).kind, 'locked');
  assert.equal(classifyError({ status: 503, message: '' }).kind, 'not_configured');
  assert.equal(classifyError({ message: 'Failed to fetch' }).kind, 'network');
  assert.match(classifyError({ message: 'x' }).hint, /OUT OF DATE/);
  assert.equal(classifyError({ status: 500, message: 'boom' }).kind, 'server');
});

test('risk badge never implies live when not live, and shows every caveat', () => {
  assert.equal(riskBadge({ station: 's', name: 'n' }).label, 'NO FORECAST');
  const b = riskBadge({ station: 's', name: 'n', state: 'WARNING', live: false, expired: false, confidence: 'low', conflict: true, official: { source: 'X', status: 'warning', freshness: 'stale' }, override: { message: 'Official floor applied' } });
  assert.equal(b.tone, 'warn');
  for (const re of [/NOT LIVE/, /Low confidence/, /disagree/, /stale/, /Official floor/]) assert.ok(b.caveats.some((c) => re.test(c)), String(re));
  assert.ok(riskBadge({ station: 's', name: 'n', state: 'SAFE', live: false, expired: true }).caveats[0].startsWith('EXPIRED'));
  assert.deepEqual(riskBadge({ station: 's', name: 'n', state: 'SAFE', live: true, expired: false, confidence: 'medium' }).caveats, []);
});

test('source problems: unavailable, failing, stale, and an empty list is itself an error', () => {
  assert.equal(sourceProblems([]).length, 1);
  const p = sourceProblems([{ source: 'cwc', state: 'never_succeeded', last_error: 'cwc: no verified endpoint' }, { source: 'a', state: 'failing', last_error: 'OSError' }, { source: 'b', state: 'stale', age_minutes: 240 }, { source: 'c', state: 'ok' }]);
  assert.deepEqual(p.map((x) => x.severity), ['error', 'error', 'warn']);
  assert.match(p[0].message, /no data from cwc/); assert.match(p[2].message, /4 h/);
});

test('banner: synthetic data is always labelled, never claimed as real-time', () => {
  assert.equal(dataBanner({ clock: 'demo', risks: [] }).kind, 'synthetic');
  assert.equal(dataBanner({ clock: 'wall', risks: [{ station: 's', name: 'n', data_provenance: 'synthetic_reconstruction' }] }).kind, 'synthetic');
  assert.match(dataBanner({ clock: 'demo' }).text, /not real flood measurements/);
  assert.equal(dataBanner({ clock: 'wall', risks: [] }).kind, 'none');
  assert.doesNotMatch(dataBanner({ clock: 'wall', risks: [{ station: 's', name: 'n' }] }).text, /real-time|live/i);
});

test('formatAge and refresh status', () => {
  assert.equal(formatAge(null), 'unknown time'); assert.equal(formatAge(0.2), 'under a minute'); assert.equal(formatAge(45), '45 min');
  assert.equal(formatAge(125), '2 h 5 min'); assert.equal(formatAge(3000), '2 days');
  assert.equal(refreshStatus(null, 0, false).text, 'Loading…');
  assert.ok(refreshStatus(0, 120_000, false).stale); assert.ok(refreshStatus(0, 1000, true).text.startsWith('REFRESH FAILING'));
});

test('SOS grouping: unacknowledged cells first, totals correct', () => {
  const mk = (id: string, lat: number, lon: number, state: string, n: number, med = false) => ({ message_id: id, lat, lon, people_count: n, medical_flag: med, state, hop_count: 1 });
  const c = clusterSos([mk('a', 26.151, 85.901, 'acknowledged', 2), mk('b', 26.152, 85.899, 'acknowledged', 1), mk('c', 27.0, 86.5, 'received', 4, true)]);
  assert.equal(c[0].unacknowledged, 1); assert.equal(c[0].people, 4); assert.equal(c[0].medical, 1);
  assert.equal(c[1].items.length, 2);
});
