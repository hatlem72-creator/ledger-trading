#!/usr/bin/env python3
"""Verify an encrypted index.html can be unlocked from pw.txt. Prints no secrets."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64

NEEDLES = ("Equinor", "Kjøpt og solgt", "The Market Ledger", "NVDA", "Virtuell simulering")
FORBIDDEN_IN_CIPHER_PAGE = ("Equinor ASA", "NVIDIA Corporation", "49 578,56", "KOG.OL")


def main() -> int:
    enc_path = Path(sys.argv[1])
    pw = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
    html = enc_path.read_text(encoding="utf-8")
    for n in FORBIDDEN_IN_CIPHER_PAGE:
        if n in html:
            print("LEAK:", n)
            return 1
    m = re.search(r"const PAYLOAD = (\{.*?\});", html)
    it = re.search(r"const ITER = (\d+);", html)
    if not m or not it:
        print("payload not found")
        return 1
    payload = json.loads(m.group(1))
    iterations = int(it.group(1))
    salt = base64.b64decode(payload["salt"])
    iv = base64.b64decode(payload["iv"])
    data = base64.b64decode(payload["data"])
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations).derive(pw.encode())
    pt = AESGCM(key).decrypt(iv, data, None).decode("utf-8")
    missing = [n for n in NEEDLES if n not in pt]
    if missing:
        print("decrypt ok but missing", missing)
        return 1
    print("decrypt ok; plaintext length", len(pt), "no leaks in wrapper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
