#!/usr/bin/env python3
"""
instagram_post.py - publica Reels de verdade, gratis, pela API oficial.

Diferente do TikTok, o Instagram PUBLICA mesmo: nao e rascunho.
Limite: 50 posts por 24h por conta. Nao consome cota do YouTube.

O QUE PRECISA EXISTIR ANTES (uma vez):
  1) Conta do Instagram no modo Profissional (Comercial ou Criador de
     conteudo). Conta pessoal nao serve.
  2) Uma Pagina do Facebook vinculada a essa conta.
  3) Um app em developers.facebook.com com o produto "Instagram Graph API".
     Em modo Desenvolvimento, com a sua conta como administradora, publica
     sem passar por Analise do App. So precisa de Analise para publicar em
     conta de terceiro.
  4) Um token de acesso de longa duracao e o ID da conta do Instagram.

DETALHE QUE PEGA TODO MUNDO: o Instagram nao recebe o arquivo. Voce da uma
URL publica e o servidor da Meta baixa de la. Por isso existe o
publicar_release.py, que sobe o mp4 num Release do GitHub e devolve a URL.

Variaveis de ambiente:
    IG_USER_ID      ID da conta do Instagram (numerico)
    IG_TOKEN        token de acesso de longa duracao

Uso:
    python3 instagram_post.py publicar "https://.../video.mp4" "legenda"
    python3 instagram_post.py renovar     # estende o token por mais 60 dias
    python3 instagram_post.py checar      # confere token, conta e limite
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

# Deixe a versao configuravel: a Meta aposenta versoes antigas regularmente.
# O valor padrao preserva a versao testada neste projeto.
GRAPH_VERSION = os.environ.get("IG_GRAPH_VERSION", "v21.0").lstrip("/")
API = f"https://graph.facebook.com/{GRAPH_VERSION}"
IG_USER_ID = os.environ.get("IG_USER_ID", "")
IG_TOKEN = os.environ.get("IG_TOKEN", "")

ESPERA_MAX = 300      # o processamento do video costuma levar 15 a 90 s
INTERVALO = 6


def log(msg):
    print(f"[instagram] {msg}", flush=True)


def _req(caminho, params=None, metodo="GET"):
    params = dict(params or {})
    params["access_token"] = IG_TOKEN
    url = f"{API}/{caminho}"
    dados = None
    if metodo == "POST":
        dados = urllib.parse.urlencode(params).encode()
    else:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=dados, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {corpo}") from None


def _exige_config():
    faltando = [n for n, v in (("IG_USER_ID", IG_USER_ID),
                               ("IG_TOKEN", IG_TOKEN)) if not v]
    if faltando:
        sys.exit("Faltam variaveis de ambiente: " + ", ".join(faltando))


def cmd_checar():
    _exige_config()
    conta = _req(IG_USER_ID, {"fields": "username,followers_count"})
    log(f"conta: @{conta.get('username')} ({conta.get('followers_count')} seguidores)")
    limite = _req(f"{IG_USER_ID}/content_publishing_limit",
                  {"fields": "quota_usage,config"})
    d = (limite.get("data") or [{}])[0]
    usado = d.get("quota_usage", "?")
    total = (d.get("config") or {}).get("quota_total", 50)
    log(f"publicacoes nas ultimas 24h: {usado} de {total}")
    return conta


def cmd_publicar(url_video, legenda=""):
    """Cria o container, espera processar, publica. Devolve o ID do post."""
    _exige_config()
    if not url_video.lower().startswith("https://"):
        sys.exit("A URL do video precisa ser https publica, sem login.")

    log("criando container")
    c = _req(f"{IG_USER_ID}/media", {
        "media_type": "REELS",
        "video_url": url_video,
        "caption": legenda[:2200],
        "share_to_feed": "true",
    }, metodo="POST")
    container = c["id"]

    log("aguardando o Instagram baixar e processar o video")
    inicio = time.time()
    while time.time() - inicio < ESPERA_MAX:
        st = _req(container, {"fields": "status_code,status"})
        estado = st.get("status_code")
        if estado == "FINISHED":
            break
        if estado == "ERROR":
            sys.exit(f"O Instagram recusou o video: {st.get('status')}")
        time.sleep(INTERVALO)
    else:
        sys.exit("Tempo esgotado no processamento. A URL esta acessivel "
                 "publicamente? Teste abrindo em aba anonima.")

    log("publicando")
    pub = _req(f"{IG_USER_ID}/media_publish",
               {"creation_id": container}, metodo="POST")
    post = pub["id"]
    log(f"OK post {post}")
    return post


def cmd_renovar():
    """Token de longa duracao dura 60 dias. Renove antes de vencer."""
    _exige_config()
    app_id = os.environ.get("IG_APP_ID", "")
    app_secret = os.environ.get("IG_APP_SECRET", "")
    if not (app_id and app_secret):
        sys.exit("Para renovar defina tambem IG_APP_ID e IG_APP_SECRET.")
    r = _req("oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": IG_TOKEN,
    })
    dias = int(r.get("expires_in", 0)) // 86400
    log(f"token renovado, vale mais {dias} dias")
    print(r["access_token"])
    log("Atualize o secret IG_TOKEN com o valor impresso acima.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "publicar":
        cmd_publicar(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    elif cmd == "renovar":
        cmd_renovar()
    elif cmd == "checar":
        cmd_checar()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
