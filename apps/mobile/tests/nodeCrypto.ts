// TEST-ONLY CryptoPort backed by node:crypto (Ed25519). The app itself uses tweetnacl (src/appCrypto.ts).
import { createPrivateKey, createPublicKey, randomUUID, sign, verify } from 'node:crypto';
import type { CryptoPort } from '../src/core/envelope.ts';

const PKCS8 = Buffer.from('302e020100300506032b657004220420', 'hex');
const SPKI = Buffer.from('302a300506032b6570032100', 'hex');

export function nodeCryptoFromSeed(seed: Buffer): CryptoPort {
  const priv = createPrivateKey({ key: Buffer.concat([PKCS8, seed]), format: 'der', type: 'pkcs8' });
  const pub = createPublicKey(priv).export({ format: 'der', type: 'spki' }).subarray(-32);
  return { publicKeyHex: pub.toString('hex'), sign: (m) => sign(null, Buffer.from(m), priv).toString('hex'), verify: nodeVerify, randomId: () => randomUUID() };
}
export function nodeVerify(pubHex: string, msg: Uint8Array, sigHex: string): boolean {
  try {
    const k = createPublicKey({ key: Buffer.concat([SPKI, Buffer.from(pubHex, 'hex')]), format: 'der', type: 'spki' });
    return verify(null, Buffer.from(msg), k, Buffer.from(sigHex, 'hex'));
  } catch { return false; }
}
import { randomBytes } from 'node:crypto';
export const newNodeCrypto = (): CryptoPort => nodeCryptoFromSeed(randomBytes(32));
