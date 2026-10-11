// UNTESTED React Native UI. Design rules from SRS 7: one state, one reason, one action; <=3 primary numbers; text+icon+colour together.
import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { api } from './api';
import { useApp } from './state';
import { useT } from './i18nContext';
import { STRINGS } from './core/i18n.ts';
import { decodePayload } from './core/envelope.ts';
import { MAP_STYLE_URL } from './config';

const LOOK = { SAFE: ['#1b7f3b', '✔'], WATCH: ['#9a6b00', '◐'], WARNING: ['#c2410c', '▲'], EVACUATE: ['#b91c1c', '■'] } as const;
const Btn = ({ label, onPress, danger }: { label: string; onPress: () => void; danger?: boolean }) => (
  <Pressable accessibilityRole="button" onPress={onPress} style={[s.btn, danger && { backgroundColor: '#b91c1c' }]}><Text style={s.btnT}>{label}</Text></Pressable>);

export function Home() {
  const { risk, status, online, loc, refresh } = useApp(); const t = useT();
  const [why, setWhy] = useState(false), [shelter, setShelter] = useState<any>(null);
  useEffect(() => { api.shelters(loc.lat, loc.lon).then((x) => setShelter(x[0] ?? null)).catch(() => {}); }, [loc]);
  const r = risk?.response;
  if (!r) return <View style={s.pad}><Text style={s.h2}>{t('status.none')}</Text><Btn label="↻" onPress={refresh} /></View>;
  const [color, icon] = LOOK[r.state];
  const f = r.forecast;
  return (
    <ScrollView contentContainerStyle={s.pad}>
      {!online && <Text style={s.banner}>{t('offline.banner', { n: status.ageMinutes ?? 0 })}</Text>}
      {r.data_provenance === 'synthetic_reconstruction' && <Text style={s.demo}>{t('demo.notice')}</Text>}
      <View style={[s.card, { borderColor: color }]}>
        <Text style={[s.state, { color }]}>{icon} {t(`state.${r.state}` as any)}</Text>
        <Text style={s.action}>{t(`action.${r.state}` as any)}</Text>
        {r.official && <Text style={s.official}>{t('official.active')}: {r.official.source} ({r.official.status})</Text>}
        {r.override && <Text style={s.official}>{r.override.message}</Text>}
        {shelter && r.state !== 'SAFE' && <Text style={s.action}>→ {shelter.name} ({shelter.distance_km} km){shelter.provenance === 'synthetic_demo' ? ' · demo' : ''}</Text>}
        {f && <Text style={s.nums}>+1h {f['1h'].q50} m   +3h {f['3h'].q50} m   +6h {f['6h'].q50} m</Text>}
        <Text style={s.meta}>{t('updated.minutes', { n: status.ageMinutes ?? r.age_minutes })} · {t(`confidence.${r.confidence}` as any)} · {t(`status.${status.mode}` as any)}</Text>
      </View>
      <Btn label={t('why')} onPress={() => setWhy(!why)} />
      {why && r.drivers.map((d) => <Text key={d.name} style={s.meta}>• {d.name}: {d.value} {d.unit} ({d.direction})</Text>)}
    </ScrollView>);
}

export function MapScreen() {
  const { loc } = useApp(); const [shelters, setSh] = useState<any[]>([]), [reports, setRp] = useState<any[]>([]);
  useEffect(() => { api.shelters(loc.lat, loc.lon).then(setSh).catch(() => {}); api.reports(loc.lat, loc.lon).then(setRp).catch(() => {}); }, [loc]);
  // MapLibre RN API differs by major version: verify imports against the installed @maplibre/maplibre-react-native.
  const ML = require('@maplibre/maplibre-react-native');
  const pts = (a: any[]) => ({ type: 'FeatureCollection', features: a.map((x) => ({ type: 'Feature', properties: { name: x.name ?? x.type }, geometry: { type: 'Point', coordinates: [x.lon, x.lat] } })) });
  return (
    <View style={{ flex: 1 }}>
      <ML.MapView style={{ flex: 1 }} mapStyle={MAP_STYLE_URL}>
        <ML.Camera centerCoordinate={[loc.lon, loc.lat]} zoomLevel={11} />
        <ML.ShapeSource id="sh" shape={pts(shelters)}><ML.CircleLayer id="shc" style={{ circleRadius: 9, circleColor: '#1d4ed8', circleStrokeWidth: 2, circleStrokeColor: '#fff' }} /></ML.ShapeSource>
        <ML.ShapeSource id="rp" shape={pts(reports)}><ML.CircleLayer id="rpc" style={{ circleRadius: 7, circleColor: '#c2410c', circleStrokeWidth: 2, circleStrokeColor: '#fff' }} /></ML.ShapeSource>
      </ML.MapView>
      <Text style={s.meta}>● shelters (blue)   ● community reports (orange, unverified)</Text>
    </View>);
}

export function Timeline() {
  const { loc } = useApp(); const [h, setH] = useState<any[]>([]);
  useEffect(() => { api.timeline(loc.lat, loc.lon).then((x) => setH(x.history)).catch(() => {}); }, [loc]);
  return <ScrollView contentContainerStyle={s.pad}>{h.slice().reverse().map((x, i) => (
    <Text key={i} style={s.meta}>{new Date(x.generated_at).toLocaleTimeString()}  {LOOK[x.state as keyof typeof LOOK][1]} {x.state}  {x.current_level_m ?? ''} m</Text>))}</ScrollView>;
}

export function Emergency() {
  const { sendSos, messages, peers, online, p2pAvailable } = useApp(); const t = useT();
  const [people, setPeople] = useState('1'), [medical, setMedical] = useState(false), [note, setNote] = useState('');
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Text style={s.h2}>{t('sos.title')}</Text>
      <Text style={s.meta}>{online ? '' : t('offline.banner', { n: 0 }).split('.')[0] + '.'} {p2pAvailable ? (peers ? t('peers.count', { n: peers }) : t('peers.none')) : 'P2P module unavailable'}</Text>
      <TextInput style={s.input} keyboardType="number-pad" value={people} onChangeText={setPeople} accessibilityLabel={t('sos.people')} />
      <View style={s.row}><Text style={s.action}>{t('sos.medical')}</Text><Switch value={medical} onValueChange={setMedical} /></View>
      <TextInput style={s.input} value={note} onChangeText={setNote} placeholder={t('sos.note')} maxLength={140} />
      <Btn danger label={t('sos.send')} onPress={() => sendSos({ people: Math.max(1, parseInt(people) || 1), medical, note })} />
      {messages.filter((m) => m.origin === 'self').map((m) => (
        <Text key={m.envelope.message_id} style={s.meta}>SOS {m.envelope.created_at.slice(11, 16)} · {t(`delivery.${m.state}` as any)}{m.relayCount ? ` (${m.relayCount})` : ''}</Text>))}
    </ScrollView>);
}

export function Reports() {
  const { loc, sendReport, messages } = useApp(); const t = useT(); const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api.reports(loc.lat, loc.lon).then(setRows).catch(() => {}); }, [loc]);
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Text style={s.h2}>{t('reports.title')}</Text>
      {['water_depth', 'blocked_road', 'stranded_person', 'bridge_structure'].map((k) => <Btn key={k} label={k.replace('_', ' ')} onPress={() => sendReport(k)} />)}
      {rows.map((r) => <Text key={r.id} style={s.meta}>{r.type} · {t('reports.unverified')} · {new Date(r.created_at).toLocaleTimeString()}</Text>)}
      {messages.filter((m) => m.envelope.message_type === 'REPORT').map((m) => <Text key={m.envelope.message_id} style={s.meta}>{decodePayload(m.envelope).type} · {m.state}</Text>)}
    </ScrollView>);
}

export function Settings() {
  const { lang, setLang, loc, setLoc } = useApp(); const t = useT();
  const [lat, setLat] = useState(String(loc.lat)), [lon, setLon] = useState(String(loc.lon));
  return (
    <ScrollView contentContainerStyle={s.pad}>
      <Text style={s.h2}>{t('settings.language')}</Text>
      <View style={s.row}><Btn label="English" onPress={() => setLang('en')} /><Btn label="हिन्दी" onPress={() => setLang('hi')} /></View>
      <Text style={s.h2}>{t('settings.location')}</Text>
      <Text style={s.meta}>Manual locality (no GPS permission required)</Text>
      <TextInput style={s.input} value={lat} onChangeText={setLat} keyboardType="numeric" />
      <TextInput style={s.input} value={lon} onChangeText={setLon} keyboardType="numeric" />
      <Btn label="OK" onPress={() => { const a = parseFloat(lat), o = parseFloat(lon); if (Math.abs(a) <= 90 && Math.abs(o) <= 180) setLoc({ lat: a, lon: o }); }} />
      <Text style={s.meta}>{Object.keys(STRINGS.en).length} strings · en/hi (Hindi draft needs native review)</Text>
    </ScrollView>);
}

export const s = StyleSheet.create({
  pad: { padding: 16, gap: 12 }, h2: { fontSize: 20, fontWeight: '700' }, card: { borderWidth: 4, borderRadius: 12, padding: 16, gap: 8 },
  state: { fontSize: 36, fontWeight: '800' }, action: { fontSize: 18 }, nums: { fontSize: 20, fontWeight: '600' }, meta: { fontSize: 14, color: '#444' },
  official: { fontSize: 16, fontWeight: '600' }, banner: { backgroundColor: '#fde68a', padding: 10, fontSize: 16 }, demo: { backgroundColor: '#e0e7ff', padding: 8 },
  btn: { backgroundColor: '#1d4ed8', padding: 16, borderRadius: 10, minHeight: 56, justifyContent: 'center' }, btnT: { color: '#fff', fontSize: 18, fontWeight: '700', textAlign: 'center' },
  input: { borderWidth: 1, borderColor: '#999', borderRadius: 8, padding: 12, fontSize: 18 }, row: { flexDirection: 'row', gap: 12, alignItems: 'center', justifyContent: 'space-between' },
});
