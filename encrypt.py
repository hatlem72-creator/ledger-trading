#!/usr/bin/env python3
"""Encrypt a plaintext HTML file into a StatiCrypt-style password gate (AES-GCM + PBKDF2)."""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITERATIONS = 250_000


WRAPPER = r"""<!doctype html>
<html lang="nb">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>The Market Ledger — låst</title>
<style>
:root{--paper:#fbf9f3;--ink:#111;}
*{box-sizing:border-box}
html,body{background:var(--paper);color:var(--ink)}
body{
  max-width:720px;margin:0 auto;padding:28px 22px 48px;
  font-family:Georgia,"Times New Roman","Liberation Serif",serif;
}
@font-face{
  font-family:"UnifrakturMaguntia";
  src:url("fonts/UnifrakturMaguntia.woff") format("woff");
  font-display:swap;
}
.masthead{text-align:center;padding-bottom:12px;border-bottom:4px double #111}
.meta{display:flex;justify-content:space-between;font-size:.78rem;letter-spacing:.12em;text-transform:uppercase;border-bottom:1px solid #111;padding:4px 0 8px}
h1{font-family:"UnifrakturMaguntia","Old English Text MT",Georgia,serif;font-size:clamp(2.6rem,8vw,4rem);font-weight:400;margin:.18em 0 .08em;line-height:1.05}
.tagline{font-style:italic;margin:0 0 6px}
.box{border:2px solid #111;margin:2.2rem auto 0;padding:28px 24px 24px;max-width:420px;text-align:center}
.box h2{margin:0 0 .4rem;text-transform:uppercase;letter-spacing:.12em;font-size:1.05rem;border:0}
.box p{margin:0 0 1rem;color:#333;font-style:italic}
label{display:block;font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px;text-align:left}
input[type=password]{
  width:100%;font:inherit;font-size:1.15rem;padding:10px 12px;
  border:1px solid #111;background:#fff;color:#111;margin-bottom:14px;
}
button{
  appearance:none;background:#111;color:#fbf9f3;border:1px solid #111;
  font:inherit;letter-spacing:.12em;text-transform:uppercase;font-size:.85rem;
  padding:10px 22px;cursor:pointer;width:100%;
}
button:hover{background:#222}
.err{color:#a40e0e;font-style:italic;min-height:1.3em;margin:10px 0 0}
footer{border-top:4px double #111;margin-top:2.4rem;padding-top:10px;font-size:.8rem;text-align:center}
</style>
</head>
<body>
  <header class="masthead">
    <div class="meta"><span>Virtuell utgave</span><span>Låst</span></div>
    <h1>The Market Ledger</h1>
    <p class="tagline">Virtuell papirhandel · ASK og IKZ</p>
  </header>
  <form class="box" id="gate" autocomplete="off">
    <h2>Dette bladet er låst</h2>
    <p>Oppgi passordet for å lese den virtuelle handelsloggen.</p>
    <label for="pw">Passord</label>
    <input id="pw" name="password" type="password" autocomplete="current-password" required autofocus>
    <button type="submit">Åpne bladet</button>
    <p class="err" id="err" role="alert"></p>
  </form>
  <footer>
    <p>Virtuell papirhandel. Innholdet er kryptert i nettleseren og kan ikke leses uten passord.</p>
  </footer>
  <script>
  const PAYLOAD = __PAYLOAD__;
  const ITER = __ITER__;

  function b64(s){
    const bin = atob(s);
    const out = new Uint8Array(bin.length);
    for (let i=0;i<bin.length;i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function decrypt(password){
    const enc = new TextEncoder();
    const salt = b64(PAYLOAD.salt);
    const iv = b64(PAYLOAD.iv);
    const data = b64(PAYLOAD.data);
    const material = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]);
    const key = await crypto.subtle.deriveKey(
      {name:"PBKDF2", salt, iterations: ITER, hash:"SHA-256"},
      material,
      {name:"AES-GCM", length:256},
      false,
      ["decrypt"]
    );
    const pt = await crypto.subtle.decrypt({name:"AES-GCM", iv}, key, data);
    return new TextDecoder().decode(pt);
  }

  const form = document.getElementById("gate");
  const err = document.getElementById("err");
  const input = document.getElementById("pw");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.textContent = "";
    const pw = input.value;
    if (!pw){ err.textContent = "Skriv inn passordet."; return; }
    try {
      const html = await decrypt(pw);
      document.open();
      document.write(html);
      document.close();
    } catch (ex) {
      err.textContent = "Feil passord, eller siden kunne ikke åpnes.";
      input.select();
    }
  });
  </script>
</body>
</html>
"""


def read_password(path: Path) -> str:
    pw = path.read_text(encoding="utf-8").strip()
    if not pw:
        raise SystemExit("password file is empty")
    return pw


def encrypt_html(plaintext: str, password: str) -> str:
    salt = os.urandom(16)
    iv = os.urandom(12)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    key = kdf.derive(password.encode("utf-8"))
    data = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    payload = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "data": base64.b64encode(data).decode("ascii"),
    }
    import json

    html = WRAPPER.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
    html = html.replace("__ITER__", str(ITERATIONS))
    return html


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: encrypt.py PLAIN.html pw.txt OUT.html", file=sys.stderr)
        return 2
    src = Path(sys.argv[1])
    pw_path = Path(sys.argv[2])
    dest = Path(sys.argv[3])
    html = encrypt_html(src.read_text(encoding="utf-8"), read_password(pw_path))
    dest.write_text(html, encoding="utf-8")
    print(f"wrote encrypted {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
