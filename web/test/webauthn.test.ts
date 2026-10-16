import { describe, expect, it } from 'vitest';
import {
  assertionToJSON, b64urlToBuf, bufToB64url, creationOptionsFromJSON, registrationToJSON, requestOptionsFromJSON,
} from '../src/api/webauthn';

const bytes = (...n: number[]) => new Uint8Array(n).buffer;

describe('base64url', () => {
  it('без +, / и = и круговой обмен', () => {
    const src = new Uint8Array([251, 255, 254, 62, 63, 0, 1]); // даёт + и / в обычном base64
    const s = bufToB64url(src.buffer);
    expect(s).not.toMatch(/[+/=]/);
    expect(new Uint8Array(b64urlToBuf(s))).toEqual(src);
  });
  it('все длины 0..64 переживают круг', () => {
    for (let n = 0; n <= 64; n++) {
      const a = new Uint8Array(n).map((_, i) => (i * 37 + n) & 255);
      expect(new Uint8Array(b64urlToBuf(bufToB64url(a)))).toEqual(a);
    }
  });
  it('известный вектор', () => {
    expect(bufToB64url(new TextEncoder().encode('hello?>').buffer)).toBe('aGVsbG8_Pg');
    expect(new TextDecoder().decode(b64urlToBuf('aGVsbG8_Pg'))).toBe('hello?>');
  });
  it('принимает view с offset', () => {
    const big = new Uint8Array([9, 9, 1, 2, 3, 9]);
    expect(bufToB64url(big.subarray(2, 5))).toBe(bufToB64url(bytes(1, 2, 3)));
  });
});

describe('options', () => {
  it('creation: challenge, user.id, excludeCredentials -> ArrayBuffer', () => {
    const o = creationOptionsFromJSON({
      challenge: bufToB64url(bytes(1, 2, 3)),
      user: { id: bufToB64url(bytes(7, 8)), name: 'n', displayName: 'N' },
      excludeCredentials: [{ id: bufToB64url(bytes(5)), type: 'public-key', transports: ['internal'] }],
      rp: { name: 'FePra' },
    });
    expect(new Uint8Array(o.challenge as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
    expect(new Uint8Array(o.user.id as ArrayBuffer)).toEqual(new Uint8Array([7, 8]));
    expect(new Uint8Array(o.excludeCredentials![0].id as ArrayBuffer)).toEqual(new Uint8Array([5]));
    expect(o.rp.name).toBe('FePra');
  });
  it('request: allowCredentials опционален', () => {
    const o = requestOptionsFromJSON({ challenge: bufToB64url(bytes(4)) });
    expect(new Uint8Array(o.challenge as ArrayBuffer)).toEqual(new Uint8Array([4]));
    expect(o.allowCredentials).toBeUndefined();
  });
});

describe('credential -> JSON', () => {
  it('registration', () => {
    const cred = {
      id: 'abc', rawId: bytes(1, 2), type: 'public-key', authenticatorAttachment: 'platform',
      response: { clientDataJSON: bytes(3), attestationObject: bytes(4), getTransports: () => ['internal'] },
      getClientExtensionResults: () => ({}),
    } as unknown as PublicKeyCredential;
    const j = registrationToJSON(cred);
    expect(j.rawId).toBe(bufToB64url(bytes(1, 2)));
    expect(j.response.attestationObject).toBe(bufToB64url(bytes(4)));
    expect(j.response.transports).toEqual(['internal']);
  });
  it('assertion: userHandle null и непустой', () => {
    const mk = (uh: ArrayBuffer | null) => ({
      id: 'x', rawId: bytes(1), type: 'public-key',
      response: { clientDataJSON: bytes(2), authenticatorData: bytes(3), signature: bytes(4), userHandle: uh },
      getClientExtensionResults: () => ({}),
    }) as unknown as PublicKeyCredential;
    expect(assertionToJSON(mk(null)).response.userHandle).toBeNull();
    expect(assertionToJSON(mk(bytes(9))).response.userHandle).toBe(bufToB64url(bytes(9)));
    expect(assertionToJSON(mk(null)).response.signature).toBe(bufToB64url(bytes(4)));
  });
});
