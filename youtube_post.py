#!/usr/bin/env python3
"""
youtube_post.py - sobe video para o YouTube (Shorts) usando a API oficial.
Gratis. Sem servico intermediario. Publicacao publica e automatica.

Por que o YouTube e a melhor aposta gratis:
    - nao precisa de auditoria pra postar no SEU proprio canal
    - publica publico de verdade, sem voce tocar
    - limite: cota de 10.000 unidades/dia, upload custa 1.600 -> 6 videos/dia

Preparacao (uma vez, no seu PC):
    1) console.cloud.google.com -> cria projeto
    2) ativa a "YouTube Data API v3"
    3) tela de consentimento OAuth -> External -> adiciona seu email
       em "Usuarios de teste"
    4) Credenciais -> ID do cliente OAuth -> tipo "App para computador"
    5) baixa o JSON e salva como client_secret.json ao lado deste script

    pip install google-auth-oauthlib google-api-python-client
    python3 youtube_post.py auth

    Abre o navegador, autoriza, e gera youtube_token.json.
    Guarde esse arquivo: e ele que permite postar sem navegador depois.

Uso:
    python3 youtube_post.py upload video.mp4 "Titulo" "Descricao" "tag1,tag2"
    python3 youtube_post.py quota
"""

import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(BASE, "client_secret.json")
TOKEN_FILE = os.path.join(BASE, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _deps():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa
        from googleapiclient.discovery import build  # noqa
        from googleapiclient.http import MediaFileUpload  # noqa
        from google.oauth2.credentials import Credentials  # noqa
        from google.auth.transport.requests import Request  # noqa
    except ImportError:
        sys.exit(
            "Faltam dependencias. Rode:\n"
            "  pip install google-auth-oauthlib google-api-python-client"
        )


def cmd_auth():
    _deps()
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not os.path.exists(CLIENT_SECRET):
        sys.exit(f"Nao achei {CLIENT_SECRET}. Baixe do Google Cloud Console.")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    # abre navegador e escuta em localhost; funciona para cliente tipo "Desktop"
    creds = flow.run_local_server(port=8765, prompt="consent", open_browser=True)

    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)
    print(f"OK. Token salvo em {TOKEN_FILE}")
    if not creds.refresh_token:
        print("AVISO: veio sem refresh_token. Revogue o acesso e rode de novo.")


def _creds():
    _deps()
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not os.path.exists(TOKEN_FILE):
        sys.exit("Sem token. Rode 'auth' primeiro, no seu PC.")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        else:
            sys.exit("Token invalido e sem refresh_token. Rode 'auth' de novo.")
    return creds


def cmd_upload(path, titulo, descricao="", tags="", privacidade="public"):
    if not os.path.isfile(path):
        sys.exit(f"Arquivo nao encontrado: {path}")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)

    body = {
        "snippet": {
            "title": titulo[:100],
            "description": descricao[:5000],
            "tags": [t.strip() for t in tags.split(",") if t.strip()][:15],
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": privacidade,
            "selfDeclaredMadeForKids": False,
            # obrigatorio declarar conteudo sintetico/gerado por IA
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(path, chunksize=8 * 1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")

    vid = resp["id"]
    print(f"OK https://www.youtube.com/watch?v={vid}")
    return vid


def cmd_quota():
    """A API nao expoe a cota. Isto so lembra a conta."""
    print("Cota diaria padrao: 10.000 unidades.")
    print("videos.insert custa 1.600 -> no maximo 6 uploads por dia.")
    print("Painel: console.cloud.google.com -> APIs e servicos -> Cotas")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "auth":
        cmd_auth()
    elif cmd == "upload":
        a = sys.argv[2:]
        cmd_upload(a[0], a[1],
                   a[2] if len(a) > 2 else "",
                   a[3] if len(a) > 3 else "",
                   a[4] if len(a) > 4 else "public")
    elif cmd == "quota":
        cmd_quota()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
