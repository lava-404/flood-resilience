// App-wide runtime: connectivity, cached risk, message store, P2P wiring, sync. UNTESTED RN glue (logic lives in core/ and is tested).
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import NetInfo from '@react-native-community/netinfo';
import { api, type Risk } from './api';
import { DEMO_LOCATION } from './config';
import { loadCrypto } from './appCrypto';
import { createEnvelope, validate, type CryptoPort } from './core/envelope.ts';
import { MessageStore, type Rec } from './core/store.ts';
import { receive } from './core/relay.ts';
import { syncOnce } from './core/sync.ts';
import { displayStatus, type CachedRisk } from './core/cache.ts';
import { loadPrefs, loadRiskCache, messagePersist, saveRiskCache, savePrefs } from './storage';
import { p2p, p2pAvailable } from './p2p';
import type { Lang } from './core/i18n.ts';

interface Ctx { lang: Lang; setLang: (l: Lang) => void; online: boolean; loc: { lat: number; lon: number }; setLoc: (l: { lat: number; lon: number }) => void;
  risk: (CachedRisk & { response: Risk }) | null; status: ReturnType<typeof displayStatus>; refresh: () => Promise<void>;
  messages: Rec[]; peers: number; p2pAvailable: boolean; sendSos: (p: { people: number; medical: boolean; note: string }) => Promise<void>;
  sendReport: (type: string) => Promise<void>; nowMs: number; ready: boolean }
const C = createContext<Ctx>(null as any);
export const useApp = () => useContext(C);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangS] = useState<Lang>('en'), [online, setOnline] = useState(true), [loc, setLocS] = useState(DEMO_LOCATION);
  const [risk, setRisk] = useState<Ctx['risk']>(null), [messages, setMessages] = useState<Rec[]>([]), [peers, setPeers] = useState(0);
  const [nowMs, setNow] = useState(Date.now()), [ready, setReady] = useState(false);
  const store = useRef(new MessageStore(messagePersist)), crypto = useRef<CryptoPort | null>(null);

  const publish = useCallback(() => {
    const now = new Date(); store.current.purge(now);
    setMessages(store.current.all());
    p2p.setOutbox(store.current.relayable(now).map((e) => ({ ...e, hop_count: e.hop_count + 1 })), store.current.ids());
  }, []);

  const trySync = useCallback(async () => { try { await syncOnce(store.current, api as any, new Date()); } catch {} publish(); }, [publish]);

  const refresh = useCallback(async () => {
    try { const r = await api.risk(loc.lat, loc.lon); const c = { response: r, fetchedAt: Date.now() }; setRisk(c); await saveRiskCache(c); await trySync(); }
    catch { /* keep the cached risk; status falls back to "saved information" */ }
  }, [loc, trySync]);

  useEffect(() => { (async () => {
    crypto.current = await loadCrypto();
    await store.current.hydrate(new Date());
    const prefs = await loadPrefs(); if (prefs) { setLangS(prefs.lang); setLocS({ lat: prefs.lat, lon: prefs.lon }); }
    setRisk(await loadRiskCache()); publish(); setReady(true);
    p2p.onMessage((raw) => { receive(store.current, [raw], crypto.current!, new Date()); publish(); });
    p2p.onPeers(setPeers);
    p2p.onSent((ids) => { ids.forEach((id) => store.current.noteRelayed(id)); publish(); });
    await p2p.start(crypto.current.publicKeyHex);
  })(); return () => { p2p.stop(); }; }, [publish]);

  useEffect(() => NetInfo.addEventListener((s) => { const on = !!s.isConnected && s.isInternetReachable !== false; setOnline(on); if (on) refresh(); }), [refresh]);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(id); }, []);
  useEffect(() => { if (ready) refresh(); }, [ready, loc.lat, loc.lon]);

  const send = async (type: 'SOS' | 'REPORT', severity: 1 | 2 | 3, payload: object) => {
    const e = createEnvelope(crypto.current!, { type, latE4: Math.round(loc.lat * 1e4), lonE4: Math.round(loc.lon * 1e4), severity, payload, now: new Date() });
    store.current.add(e, 'self', new Date()); publish();     // queued locally FIRST: works with no internet and no AWS
    if (online) await trySync();
  };
  const ctx: Ctx = { lang, setLang: (l) => { setLangS(l); savePrefs({ lang: l, ...loc, useGps: false }); }, online, loc,
    setLoc: (l) => { setLocS(l); savePrefs({ lang, ...l, useGps: false }); }, risk, status: displayStatus(risk, nowMs, online), refresh, messages, peers, p2pAvailable, nowMs, ready,
    sendSos: ({ people, medical, note }) => send('SOS', 3, { people_count: people, medical, note: note.slice(0, 140) }),
    sendReport: (type) => send('REPORT', 1, { type }) };
  return <C.Provider value={ctx}>{children}</C.Provider>;
}
export { validate };
