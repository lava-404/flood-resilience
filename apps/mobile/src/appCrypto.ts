// Device identity: a pseudonymous Ed25519 key kept in the Android Keystore-backed store. UNTESTED.
import 'react-native-get-random-values';
import nacl from 'tweetnacl';
import * as Keychain from 'react-native-keychain';
import type { CryptoPort } from './core/envelope.ts';

const hex = (b: Uint8Array) => Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
const fromHex = (s: string) => Uint8Array.from(s.match(/../g) ?? [], (h) => parseInt(h, 16));

export async function loadCrypto(): Promise<CryptoPort> {
  const saved = await Keychain.getGenericPassword({ service: 'fr-identity' });
  let seed: Uint8Array;
  if (saved) seed = fromHex(saved.password);
  else { seed = nacl.randomBytes(32); await Keychain.setGenericPassword('seed', hex(seed), { service: 'fr-identity' }); }
  const kp = nacl.sign.keyPair.fromSeed(seed);
  return {
    publicKeyHex: hex(kp.publicKey),
    sign: (m) => hex(nacl.sign.detached(m, kp.secretKey)),
    verify: (pub, m, sig) => { try { return nacl.sign.detached.verify(m, fromHex(sig), fromHex(pub)); } catch { return false; } },
    randomId: () => hex(nacl.randomBytes(16)),
  };
}
