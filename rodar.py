#!/usr/bin/env python3
"""
rodar.py - uma execucao = um video gerado e postado.

Chamado pelo cron tres vezes por dia. Cada chamada:
    1. pega o proximo tema ainda nao usado de temas.txt
    2. manda o MoneyPrinterTurbo gerar o video (roteiro pelo LLM configurado)
    3. posta no YouTube
    4. manda para a caixa de entrada do TikTok, se estiver configurado
    5. marca o tema como usado

Uso:
    python3 rodar.py            # gera e posta
    python3 rodar.py --teste    # gera e NAO posta
"""

import datetime
import json
import os
import random
import re
import subprocess
import sys
import uuid

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(BASE, "MoneyPrinterTurbo")
_venv = os.path.join(BASE, "venv", "bin", "python")
# Na VM existe venv. No GitHub Actions nao existe: usa o Python corrente.
VENV_PY = _venv if os.path.exists(_venv) else sys.executable
TEMAS = os.path.join(BASE, "temas.txt")
USADOS = os.path.join(BASE, "usados.txt")
HISTORICO = os.path.join(BASE, "historico.jsonl")

TESTE = "--teste" in sys.argv
VOZ = "pt-BR-ThalitaMultilingualNeural-Female"
RITMO = "1.18"
MAX_MB = 95  # limite pratico para nao esbarrar em limite de plataforma


def agora():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{agora()}] {msg}", flush=True)


# ------------------------------------------------------------------ tema do dia
def proximo_tema():
    if not os.path.exists(TEMAS):
        sys.exit(f"Sem {TEMAS}")

    usados = set()
    if os.path.exists(USADOS):
        usados = {l.strip() for l in open(USADOS, encoding="utf-8") if l.strip()}

    linhas = []
    for l in open(TEMAS, encoding="utf-8"):
        l = l.strip()
        if not l or l.startswith("#") or "|" not in l:
            continue
        linhas.append(l)

    disponiveis = [l for l in linhas if l.split("|")[1].strip() not in usados]

    if not disponiveis:
        log("Todos os temas ja rodaram. Zerando a lista e recomecando.")
        open(USADOS, "w").close()
        disponiveis = linhas

    return random.choice(disponiveis)


def marcar_usado(tema):
    with open(USADOS, "a", encoding="utf-8") as f:
        f.write(tema + "\n")


# --------------------------------------------------------------------- geracao
def gerar(tema, termos):
    task_id = str(uuid.uuid4())
    cmd = [
        VENV_PY, "cli.py",
        "--video-subject", tema,
        "--video-terms", termos,
        "--video-language", "pt-BR",
        "--video-source", "pexels",
        "--video-aspect", "9:16",
        "--voice-name", VOZ,
        "--voice-rate", RITMO,
        "--subtitle-enabled",
        "--font-name", "BeVietnamPro-Bold.ttf",
        "--font-size", "60",
        "--stroke-width", "2",
        "--bgm-type", "random",
        "--bgm-volume", "0.12",
        "--video-transition-mode", "fade-in",
        "--video-clip-duration", "5",
        "--paragraph-number", "4",
        "--n-threads", str(max(2, os.cpu_count() or 2)),
        "--task-id", task_id,
    ]

    env = dict(os.environ)
    env["SSL_CERT_FILE"] = "/etc/ssl/certs/ca-certificates.crt"
    env["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    log(f"Gerando: {tema}")
    r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True,
                       text=True, timeout=60 * 45)

    saida = os.path.join(REPO, "storage", "tasks", task_id, "final-1.mp4")
    if r.returncode != 0 or not os.path.exists(saida):
        tudo = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        erros = [l for l in tudo.splitlines() if "ERROR" in l or "error=" in l]
        log("FALHOU na geracao.")
        for l in (erros or tudo.splitlines())[-5:]:
            log("   " + re.sub(r"\x1b\[[0-9;]*m", "", l)[:260])
        if "api_key" in tudo or "401" in tudo:
            log("   >> parece falta de chave de LLM. Pegue uma gratis em")
            log("      aistudio.google.com/apikey e ponha gemini_api_key no config.toml")
        return None, None

    # roteiro, para usar na descricao
    roteiro = ""
    js = os.path.join(REPO, "storage", "tasks", task_id, "script.json")
    if os.path.exists(js):
        try:
            roteiro = json.load(open(js, encoding="utf-8")).get("script", "") or ""
        except Exception:
            pass

    mb = os.path.getsize(saida) / 1024 / 1024
    log(f"Gerado: {mb:.0f} MB")

    if mb > MAX_MB:
        leve = saida.replace(".mp4", "_leve.mp4")
        log("Arquivo grande, recomprimindo")
        subprocess.run(
            ["ffmpeg", "-y", "-i", saida, "-c:v", "libx264", "-crf", "27",
             "-preset", "veryfast", "-maxrate", "4M", "-bufsize", "8M",
             "-c:a", "aac", "-b:a", "128k", leve, "-loglevel", "error"],
            check=False, timeout=60 * 20,
        )
        if os.path.exists(leve):
            saida = leve

    return saida, roteiro


# -------------------------------------------------------------------- postagem
def titulo_de(tema):
    t = tema.strip().rstrip(".")
    return (t[:97] + "...") if len(t) > 100 else t


def postar_youtube(caminho, tema, roteiro, tags):
    sys.path.insert(0, BASE)
    try:
        import youtube_post
    except Exception as e:
        log(f"youtube_post indisponivel: {e}")
        return None

    if not os.path.exists(os.path.join(BASE, "youtube_token.json")):
        log("Sem youtube_token.json. Pulando o YouTube.")
        return None

    desc = (roteiro.strip()[:900] + "\n\n#shorts " +
            " ".join("#" + t.strip().replace(" ", "") for t in tags.split(",")[:5]))
    try:
        return youtube_post.cmd_upload(caminho, titulo_de(tema), desc, tags, "public")
    except SystemExit as e:
        log(f"YouTube falhou: {e}")
    except Exception as e:
        log(f"YouTube falhou: {e}")
    return None


def postar_tiktok(caminho):
    sys.path.insert(0, BASE)
    if not os.path.exists(os.path.join(BASE, "tiktok_tokens.json")):
        log("Sem tiktok_tokens.json. Pulando o TikTok.")
        return False
    try:
        import tiktok_post
        tiktok_post.cmd_upload(caminho)
        return True
    except SystemExit as e:
        log(f"TikTok falhou: {e}")
    except Exception as e:
        log(f"TikTok falhou: {e}")
    return False


# ------------------------------------------------------------------------ main
def main():
    log("=" * 55)
    linha = proximo_tema()
    partes = [p.strip() for p in linha.split("|")]
    nicho, tema, termos = (partes + ["", "", ""])[:3]
    tags = {"mar": "oceano,ciencia,curiosidades",
            "dinheiro": "financas,dinheiro,economia",
            "espiritual": "misterio,historia,curiosidades"}.get(nicho, "curiosidades")

    caminho, roteiro = gerar(tema, termos)
    if not caminho:
        sys.exit(1)

    if TESTE:
        log(f"MODO TESTE. Video em {caminho}. Nada foi postado.")
        return

    vid = postar_youtube(caminho, tema, roteiro, tags)
    tk = postar_tiktok(caminho)
    marcar_usado(tema)

    with open(HISTORICO, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "quando": agora(), "nicho": nicho, "tema": tema,
            "arquivo": caminho, "youtube": vid, "tiktok_rascunho": tk,
        }, ensure_ascii=False) + "\n")

    log(f"Fim. youtube={vid} tiktok_rascunho={tk}")


if __name__ == "__main__":
    main()
