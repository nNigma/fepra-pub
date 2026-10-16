"""CLI: ``python -m tj.services.push_cli gen-keys`` — печатает пару VAPID-ключей для .env."""
from __future__ import annotations

import base64
import sys


def gen_keys() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01
    v = Vapid01()
    v.generate_keys()
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    priv = b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
    pub = b64(v.public_key.public_bytes(serialization.Encoding.X962,
                                        serialization.PublicFormat.UncompressedPoint))
    return priv, pub


def main(argv: list[str]) -> int:
    if argv[:1] != ["gen-keys"]:
        print("usage: python -m tj.services.push_cli gen-keys", file=sys.stderr)
        return 2
    priv, pub = gen_keys()
    print(f"FEPRA_VAPID_PRIVATE={priv}\nFEPRA_VAPID_PUBLIC={pub}\n"
          "FEPRA_VAPID_SUBJECT=mailto:you@example.com")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
