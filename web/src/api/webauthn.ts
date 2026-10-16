// WebAuthn: сериализация ArrayBuffer <-> base64url для обмена с сервером (py-webauthn).

export function bufToB64url(buf: ArrayBuffer | ArrayBufferView): string {
  // isView, а не instanceof ArrayBuffer: буферы из другого realm (iframe, jsdom) не проходят instanceof
  const bytes = ArrayBuffer.isView(buf)
    ? new Uint8Array(buf.buffer, buf.byteOffset, buf.byteLength)
    : new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function b64urlToBuf(s: string): ArrayBuffer {
  const pad = s.length % 4 === 0 ? '' : '='.repeat(4 - (s.length % 4));
  const bin = atob(s.replace(/-/g, '+').replace(/_/g, '/') + pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

interface CredDescJSON {
  id: string;
  type: string;
  transports?: string[];
}

export interface CreationOptionsJSON {
  challenge: string;
  user: { id: string; name: string; displayName: string };
  excludeCredentials?: CredDescJSON[];
  [k: string]: unknown;
}

export interface RequestOptionsJSON {
  challenge: string;
  allowCredentials?: CredDescJSON[];
  [k: string]: unknown;
}

function descriptors(list?: CredDescJSON[]): PublicKeyCredentialDescriptor[] | undefined {
  return list?.map((c) => ({
    id: b64urlToBuf(c.id),
    type: 'public-key' as const,
    transports: c.transports as AuthenticatorTransport[] | undefined,
  }));
}

export function creationOptionsFromJSON(o: CreationOptionsJSON): PublicKeyCredentialCreationOptions {
  return {
    ...(o as unknown as PublicKeyCredentialCreationOptions),
    challenge: b64urlToBuf(o.challenge),
    user: { ...o.user, id: b64urlToBuf(o.user.id) },
    excludeCredentials: descriptors(o.excludeCredentials),
  };
}

export function requestOptionsFromJSON(o: RequestOptionsJSON): PublicKeyCredentialRequestOptions {
  return {
    ...(o as unknown as PublicKeyCredentialRequestOptions),
    challenge: b64urlToBuf(o.challenge),
    allowCredentials: descriptors(o.allowCredentials),
  };
}

export interface RegistrationJSON {
  id: string;
  rawId: string;
  type: string;
  response: { clientDataJSON: string; attestationObject: string; transports?: string[] };
  authenticatorAttachment?: string | null;
  clientExtensionResults: unknown;
}

export interface AssertionJSON {
  id: string;
  rawId: string;
  type: string;
  response: {
    clientDataJSON: string;
    authenticatorData: string;
    signature: string;
    userHandle: string | null;
  };
  authenticatorAttachment?: string | null;
  clientExtensionResults: unknown;
}

export function registrationToJSON(c: PublicKeyCredential): RegistrationJSON {
  const r = c.response as AuthenticatorAttestationResponse;
  return {
    id: c.id,
    rawId: bufToB64url(c.rawId),
    type: c.type,
    response: {
      clientDataJSON: bufToB64url(r.clientDataJSON),
      attestationObject: bufToB64url(r.attestationObject),
      transports: typeof r.getTransports === 'function' ? r.getTransports() : undefined,
    },
    authenticatorAttachment: c.authenticatorAttachment,
    clientExtensionResults: c.getClientExtensionResults(),
  };
}

export function assertionToJSON(c: PublicKeyCredential): AssertionJSON {
  const r = c.response as AuthenticatorAssertionResponse;
  return {
    id: c.id,
    rawId: bufToB64url(c.rawId),
    type: c.type,
    response: {
      clientDataJSON: bufToB64url(r.clientDataJSON),
      authenticatorData: bufToB64url(r.authenticatorData),
      signature: bufToB64url(r.signature),
      userHandle: r.userHandle ? bufToB64url(r.userHandle) : null,
    },
    authenticatorAttachment: c.authenticatorAttachment,
    clientExtensionResults: c.getClientExtensionResults(),
  };
}

export function passkeysSupported(): boolean {
  return typeof window !== 'undefined' && 'PublicKeyCredential' in window && !!navigator.credentials;
}
