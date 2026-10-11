// Dependency-free base64 + UTF-8 helpers (identical output to Python's base64 module).
const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
export function bytesToB64(b: Uint8Array): string {
  let o = '';
  for (let i = 0; i < b.length; i += 3) {
    const n = (b[i] << 16) | ((b[i + 1] ?? 0) << 8) | (b[i + 2] ?? 0);
    o += A[(n >> 18) & 63] + A[(n >> 12) & 63] + (i + 1 < b.length ? A[(n >> 6) & 63] : '=') + (i + 2 < b.length ? A[n & 63] : '=');
  }
  return o;
}
export function b64ToBytes(s: string): Uint8Array {
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(s)) throw new Error('bad base64');
  const pad = s.endsWith('==') ? 2 : s.endsWith('=') ? 1 : 0;
  const out = new Uint8Array((s.length / 4) * 3 - pad);
  let k = 0;
  for (let i = 0; i < s.length; i += 4) {
    const n = [0, 1, 2, 3].reduce((a, j) => (a << 6) | (s[i + j] === '=' ? 0 : A.indexOf(s[i + j])), 0);
    for (const sh of [16, 8, 0]) if (k < out.length) out[k++] = (n >> sh) & 255;
  }
  return out;
}
// NOTE: relies on global TextEncoder/TextDecoder (present in Node; in React Native add a polyfill if Hermes lacks it).
export const utf8 = (s: string): Uint8Array => new TextEncoder().encode(s);
export const fromUtf8 = (b: Uint8Array): string => new TextDecoder().decode(b);
