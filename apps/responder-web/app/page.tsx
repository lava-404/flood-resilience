'use client';
// UNTESTED UI (Next.js could not be installed where this was written); its logic lives in ../lib/view.ts, which IS unit-tested.
// The bearer token is typed by the operator and kept ONLY in memory. Replace it with Cognito/OIDC roles before any real use.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { classifyError, clusterSos, dataBanner, formatAge, refreshStatus, riskBadge, sourceProblems, type ApiError, type Sos } from '../lib/view';

const API = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000';
const TONE: Record<string, string> = { ok: '#1b7f3b', watch: '#9a6b00', warn: '#c2410c', danger: '#b91c1c', unknown: '#555' };
const ICON: Record<string, string> = { ok: '✔', watch: '◐', warn: '▲', danger: '■', unknown: '?' };

async function get(path: string, token: string, init?: RequestInit) {
  let r: Response;
  try { r = await fetch(API + path, { ...init, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } }); }
  catch (e: any) { throw { message: String(e?.message ?? e) } as ApiError; }
  if (!r.ok) throw { status: r.status, message: `${path}: HTTP ${r.status}` } as ApiError;
  return r.json();
}

export default function Page() {
  const [token, setToken] = useState('');
  const [data, setData] = useState<any>(null), [sos, setSos] = useState<Sos[]>([]);
  const [err, setErr] = useState<ApiError | null>(null), [lastOk, setLastOk] = useState<number | null>(null), [loading, setLoading] = useState(false), [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, s] = await Promise.all([get('/v1/responder/overview', token), get('/v1/responder/sos', token)]);
      setData(o); setSos(s); setErr(null); setLastOk(Date.now());
    } catch (e: any) {
      setErr(e as ApiError);
      if (e?.status === 401 || e?.status === 429) { setToken(''); setData(null); }   // back to sign-in; never keep showing data after auth loss
    } finally { setLoading(false); }
  }, [token]);

  useEffect(() => { if (!token) return; load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [token, load]);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(id); }, []);
  const clusters = useMemo(() => clusterSos(sos), [sos]);
  const ack = async (id: string) => { try { await get(`/v1/responder/sos/${id}/ack`, token, { method: 'POST' }); await load(); } catch (e: any) { setErr(e); } };

  if (!token) return <SignIn onSubmit={setToken} error={err} />;
  const banner = dataBanner(data), problems = sourceProblems(data?.source_health), refresh = refreshStatus(lastOk, now, !!err);
  const e = err ? classifyError(err) : null;

  return (
    <main>
      <h1>FloodResilience: Responder Console</h1>
      <p role="status" style={{ background: banner.kind === 'synthetic' ? '#e0e7ff' : '#f3f4f6', padding: 8 }}><b>{banner.text}</b></p>
      <p style={{ color: refresh.stale ? '#b91c1c' : '#444' }}>{loading && !data ? 'Loading…' : refresh.text} {data && <>As-of time on the server: {new Date(data.as_of).toLocaleString()} ({data.clock} clock)</>}</p>
      {e && <p role="alert" style={{ color: '#b91c1c', border: '2px solid #b91c1c', padding: 8 }}><b>{e.title}.</b> {e.hint}</p>}
      {!data && !e && <p>Loading…</p>}
      {data && <>
        {problems.length > 0 && <section aria-label="Source problems" style={{ border: '2px solid #c2410c', padding: 8 }}>
          <b>Data source problems</b><ul>{problems.map((p) => <li key={p.source} style={{ color: p.severity === 'error' ? '#b91c1c' : '#9a6b00' }}>{p.message}</li>)}</ul></section>}
        <h2>Risk by station</h2>
        {data.risks.length === 0 ? <p>No stations are configured.</p> :
          <table cellPadding={6}><thead><tr><th>Station</th><th>State</th><th>Confidence</th><th>Age</th><th>Official</th><th>Caveats</th></tr></thead><tbody>
            {data.risks.map((r: any) => { const b = riskBadge(r); return (
              <tr key={r.station}><td>{r.name}</td><td style={{ color: TONE[b.tone], fontWeight: 700 }}>{ICON[b.tone]} {b.label}</td><td>{r.confidence ?? '-'}</td>
                <td>{r.age_minutes != null ? formatAge(r.age_minutes) : '-'}</td><td>{r.official ? `${r.official.source}: ${r.official.status}` : '-'}</td>
                <td>{b.caveats.map((c, i) => <div key={i}>{c}</div>)}</td></tr>); })}
          </tbody></table>}
        <h2>Source health</h2>
        <table cellPadding={6}><thead><tr><th>Source</th><th>State</th><th>Last success</th><th>Age</th><th>Last status</th><th>Error</th></tr></thead><tbody>
          {data.source_health.map((h: any) => <tr key={h.source}><td>{h.source}</td><td style={{ fontWeight: 700, color: h.state === 'ok' ? '#1b7f3b' : '#b91c1c' }}>{h.state}</td>
            <td>{h.last_success_at ? new Date(h.last_success_at).toLocaleString() : 'never'}</td><td>{h.age_minutes != null ? formatAge(h.age_minutes) : '-'}</td><td>{h.last_status}</td><td>{h.last_error}</td></tr>)}</tbody></table>
        <p>Newest forecast age: {formatAge(data.ops.forecast_age_minutes >= 9999 ? null : data.ops.forecast_age_minutes)}{data.ops.forecast_age_minutes >= 9999 && ' (no forecast has ever been generated)'}</p>
        <h2>SOS messages ({sos.length})</h2>
        {sos.length === 0 && <p>No SOS messages received.</p>}
        {clusters.map((c) => (
          <section key={c.cell} style={{ border: '1px solid #999', margin: '8px 0', padding: 8 }}>
            <b>Grid cell {c.cell} (~5 km)</b>: {c.items.length} SOS, {c.people} people, {c.medical} medical, {c.unacknowledged} unacknowledged
            <table cellPadding={4}><tbody>{c.items.map((s: any) => (
              <tr key={s.message_id}><td>{new Date(s.created_at).toLocaleTimeString()}</td><td>{s.lat.toFixed(4)}, {s.lon.toFixed(4)}</td><td>{s.people_count ?? '?'} ppl{s.medical_flag ? ' · MEDICAL' : ''}</td>
                <td>{s.hop_count} hop(s) (unsigned, advisory) via {s.received_via}</td><td>{s.note}</td><td>{s.state}</td>
                <td>{s.state === 'received' && <button onClick={() => ack(s.message_id)}>Acknowledge</button>}</td></tr>))}</tbody></table>
          </section>))}
      </>}
    </main>);
}

function SignIn({ onSubmit, error }: { onSubmit: (t: string) => void; error: ApiError | null }) {
  const [v, setV] = useState(''); const e = error ? classifyError(error) : null;
  return <main><h1>Responder sign-in</h1>
    {e && <p role="alert" style={{ color: '#b91c1c' }}><b>{e.title}.</b> {e.hint}</p>}
    <input type="password" value={v} onChange={(x) => setV(x.target.value)} placeholder="Responder token" aria-label="Responder token" />
    <button onClick={() => onSubmit(v)} disabled={!v}>Open console</button></main>;
}
