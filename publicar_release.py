#!/usr/bin/env python3
"""
publicar_release.py - poe o mp4 num Release do GitHub e devolve a URL publica.

Existe porque o Instagram nao aceita upload de arquivo: ele exige uma URL
https publica e vai buscar o video de la. Release de repositorio publico
serve, e de graca: nao conta como armazenamento de artefato, nao engorda o
repositorio, e a URL nao expira.

Variaveis de ambiente:
    GITHUB_TOKEN         o proprio token do Actions ja serve
    GITHUB_REPOSITORY    ex: betaoa/AAAA  (o Actions define sozinho)

Uso:
    python3 publicar_release.py video.mp4 [tag]
    -> imprime a URL publica na ultima linha
"""

import datetime
import json
import os
import re
import sys
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
API = "https://api.github.com"


def log(msg):
    print(f"[release] {msg}", file=sys.stderr, flush=True)


def _req(url, dados=None, metodo="GET", tipo="application/json"):
    corpo = None
    if dados is not None:
        corpo = dados if isinstance(dados, bytes) else json.dumps(dados).encode()
    req = urllib.request.Request(url, data=corpo, method=metodo)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if corpo is not None:
        req.add_header("Content-Type", tipo)
    with urllib.request.urlopen(req, timeout=300) as r:
        texto = r.read().decode()
        return json.loads(texto) if texto else {}


def garantir_release(tag):
    try:
        return _req(f"{API}/repos/{REPO}/releases/tags/{tag}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    log(f"criando release {tag}")
    return _req(f"{API}/repos/{REPO}/releases", {
        "tag_name": tag,
        "name": tag,
        "body": "Videos gerados pelo videobot. Serve de hospedagem publica "
                "para o Instagram buscar o arquivo.",
    }, metodo="POST")


def subir(caminho, tag="videos"):
    if not (TOKEN and REPO):
        sys.exit("Faltam GITHUB_TOKEN e GITHUB_REPOSITORY.")
    if not os.path.isfile(caminho):
        sys.exit(f"Arquivo nao encontrado: {caminho}")

    rel = garantir_release(tag)
    canal = re.sub(r"[^a-z0-9_-]", "", os.environ.get("CANAL", "geral").lower())
    instante = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    nome = f"{canal}-{instante}-{os.path.basename(caminho)}"

    # Nunca substitui o asset que a Meta pode estar baixando neste momento.
    # Antes de subir um novo, remove apenas os bem antigos do mesmo canal.
    antigos = sorted(
        (a for a in rel.get("assets", []) if a.get("name", "").startswith(canal + "-")),
        key=lambda a: a.get("created_at", ""), reverse=True,
    )
    for a in antigos[30:]:
        log(f"limpando asset antigo {a['name']}")
        _req(f"{API}/repos/{REPO}/releases/assets/{a['id']}", metodo="DELETE")

    with open(caminho, "rb") as f:
        dados = f.read()
    log(f"enviando {len(dados) // 1048576} MB")

    up = rel["upload_url"].split("{")[0] + f"?name={nome}"
    asset = _req(up, dados, metodo="POST", tipo="video/mp4")
    url = asset["browser_download_url"]
    log("pronto")
    print(url)
    return url


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    subir(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "videos")
