// Bridge to the Kotlin module (apps/mobile/android-native). UNTESTED: needs two real Android devices.
// Contract: JS owns the store. setOutbox() receives envelopes ALREADY hop-incremented; native only filters by the peer's known ids.
import { NativeEventEmitter, NativeModules, PermissionsAndroid, Platform } from 'react-native';
import type { Envelope } from './core/envelope.ts';

const native = NativeModules.FloodP2p as undefined | {
  start(peerId: string): Promise<void>; stop(): Promise<void>; setOutbox(json: string): void;
  addListener(e: string): void; removeListeners(n: number): void };

export const p2pAvailable = !!native;
const emitter = native ? new NativeEventEmitter(NativeModules.FloodP2p) : null;

export const p2p = {
  start: async (peerId: string) => {
    if (!native || Platform.OS !== 'android') return;
    const perms = ((Platform.Version as number) >= 33 ? ['android.permission.NEARBY_WIFI_DEVICES'] : ['android.permission.ACCESS_FINE_LOCATION']) as any[];
    const r = await PermissionsAndroid.requestMultiple(perms);
    if (Object.values(r).every((v) => v === 'granted')) await native.start(peerId);   // without consent, SOS queueing still works; only relay is off
  },
  stop: () => native?.stop() ?? Promise.resolve(),
  setOutbox: (send: Envelope[], known: string[]) => native?.setOutbox(JSON.stringify({ send, known })),
  onMessage: (cb: (raw: unknown, from: string) => void) => emitter?.addListener('p2pMessage', (e: { json: string; from: string }) => { try { cb(JSON.parse(e.json), e.from); } catch {} }),
  onPeers: (cb: (n: number) => void) => emitter?.addListener('p2pPeers', (e: { count: number }) => cb(e.count)),
  onSent: (cb: (ids: string[]) => void) => emitter?.addListener('p2pSent', (e: { ids: string[] }) => cb(e.ids)),
};
