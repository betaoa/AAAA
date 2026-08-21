#!/usr/bin/env python3
"""
tiktok_post.py - envia video para a caixa de entrada (rascunho) do TikTok
usando o proprio app de desenvolvedor do usuario. Sem servico pago.

Fluxo (roda uma vez):
    1) python3 tiktok_post.py auth-url
       -> abre a URL no navegador, autoriza, e o TikTok te redireciona
          para o seu redirect_uri com ?code=XXXX na barra de endereco.
    2) python3 tiktok_post.py token "COLE_O_CODE_AQUI"
       -> salva access_token e refresh_token em tiktok_tokens.json

Uso diario:
    python3 tiktok_post.py upload video.mp4
    -> o video cai na sua caixa de entrada do TikTok. Voce abre o app,
       adiciona audio/legenda e publica.

Por que rascunho e nao publicacao direta:
    App sem auditoria da TikTok so consegue postar em modo privado.
    A auditoria leva de 2 a 6 semanas e pode ser negada. O envio para a
    caixa de entrada funciona SEM auditoria e e gratuito.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse

import requests

# ---------------------------------------------------------------- configuracao
# Preencha com os dados do seu app em https://developers.tiktok.com
CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "")

SCOPES = "user.info.basic,video.upload"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiktok_tokens.json")
PKCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tiktok_pkce")

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

CHUNK = 10 * 1024 * 1024  # 10 MB


def _need_config():
    faltando = [n for n, v in (
        ("TIKTOK_CLIENT_KEY", CLIENT_KEY),
        ("TIKTOK_CLIENT_SECRET", CLIENT_SECRET),
        ("TIKTOK_REDIRECT_URI", REDIRECT_URI),
    ) if not v]
    if faltando:
        sys.exit("Faltam variaveis de ambiente: " + ", ".join(faltando))


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(path, 0o600)


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ passo 1: auth
def cmd_auth_url(use_pkce=True):
    _need_config()
    state = secrets.token_urlsafe(16)
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    if use_pkce:
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
        _save(PKCE_FILE, {"verifier": verifier, "state": state})
    else:
        _save(PKCE_FILE, {"state": state})

    print("\nAbra esta URL no navegador, autorize, e copie o valor de 'code'")
    print("da barra de endereco depois do redirecionamento:\n")
    print(AUTH_URL + "?" + urllib.parse.urlencode(params))
    print()


# ----------------------------------------------------------------- passo 2: token
def cmd_token(code):
    _need_config()
    code = urllib.parse.unquote(code.strip())
    pkce = _load(PKCE_FILE) or {}
    data = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }
    if pkce.get("verifier"):
        data["code_verifier"] = pkce["verifier"]

    r = requests.post(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    j = r.json()
    if "access_token" not in j:
        sys.exit(f"Falhou ao trocar o code: {json.dumps(j, ensure_ascii=False)}")
    _save(TOKEN_FILE, j)
    print(f"OK. Token salvo em {TOKEN_FILE}")
    print(f"open_id: {j.get('open_id')}  expira em {j.get('expires_in')}s")


def cmd_refresh():
    _need_config()
    tok = _load(TOKEN_FILE) or sys.exit("Sem token salvo. Rode 'token' primeiro.")
    r = requests.post(
        TOKEN_URL,
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    j = r.json()
    if "access_token" not in j:
        sys.exit(f"Falhou o refresh: {json.dumps(j, ensure_ascii=False)}")
    _save(TOKEN_FILE, j)
    print("Token renovado.")
    return j["access_token"]


def _access_token():
    tok = _load(TOKEN_FILE)
    if not tok:
        sys.exit("Sem token salvo. Rode 'auth-url' e depois 'token'.")
    return tok["access_token"]


# ---------------------------------------------------------------- passo 3: upload
def cmd_upload(path, tentar_refresh=True):
    if not os.path.isfile(path):
        sys.exit(f"Arquivo nao encontrado: {path}")

    size = os.path.getsize(path)
    if size > 4 * 1024**3:
        sys.exit("Arquivo maior que 4 GB, limite do TikTok.")

    # O TikTok exige chunks entre 5 MB e 64 MB, e o ultimo pode ser maior.
    if size <= CHUNK:
        chunk_size, total_chunks = size, 1
    else:
        chunk_size = CHUNK
        total_chunks = size // chunk_size

    token = _access_token()
    r = requests.post(
        INIT_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            }
        },
        timeout=60,
    )
    j = r.json()
    err = (j.get("error") or {}).get("code", "")
    if err and err != "ok":
        if err in ("access_token_invalid", "access_token_expired") and tentar_refresh:
            cmd_refresh()
            return cmd_upload(path, tentar_refresh=False)
        sys.exit(f"init falhou: {json.dumps(j, ensure_ascii=False)}")

    publish_id = j["data"]["publish_id"]
    upload_url = j["data"]["upload_url"]
    print(f"init ok. publish_id={publish_id}")

    with open(path, "rb") as f:
        for i in range(total_chunks):
            start = i * chunk_size
            # o ultimo chunk leva todo o resto
            end = size - 1 if i == total_chunks - 1 else start + chunk_size - 1
            f.seek(start)
            blob = f.read(end - start + 1)
            pr = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(blob)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
                data=blob,
                timeout=300,
            )
            print(f"  chunk {i+1}/{total_chunks} -> HTTP {pr.status_code}")
            if pr.status_code not in (200, 201, 206):
                sys.exit(f"upload do chunk falhou: {pr.text[:300]}")

    print("\nEnviado. Abra o TikTok: o video esta na sua caixa de entrada,")
    print("como rascunho, esperando voce publicar.")
    cmd_status(publish_id)


def cmd_status(publish_id):
    token = _access_token()
    r = requests.post(
        STATUS_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={"publish_id": publish_id},
        timeout=30,
    )
    try:
        j = r.json()
        print("status:", json.dumps(j.get("data", j), ensure_ascii=False))
    except Exception:
        print("status HTTP", r.status_code, r.text[:200])


# ------------------------------------------------------------------------- main
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "auth-url":
        cmd_auth_url(use_pkce="--no-pkce" not in sys.argv)
    elif cmd == "token":
        cmd_token(sys.argv[2])
    elif cmd == "refresh":
        cmd_refresh()
    elif cmd == "upload":
        cmd_upload(sys.argv[2])
    elif cmd == "status":
        cmd_status(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
