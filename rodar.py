#!/usr/bin/env python3
"""
rodar.py - uma execucao = um video gerado e postado.

Chamado por videobot.py para um canal e horario. Cada chamada:
    1. pega o proximo tema ainda nao usado de temas.txt
    2. manda o MoneyPrinterTurbo gerar o video (roteiro pelo LLM configurado)
    3. publica nas plataformas configuradas para o canal
    4. registra o resultado separado de cada plataforma
    5. marca o tema como usado quando ao menos uma publicacao funciona

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
from pathlib import Path

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(BASE, "MoneyPrinterTurbo")
_venv = os.path.join(BASE, "venv", "bin", "python")
# Na VM existe venv. No GitHub Actions nao existe: usa o Python corrente.
VENV_PY = _venv if os.path.exists(_venv) else sys.executable
# Um canal por execucao. videobot.py preenche estes valores a partir de
# config/canais.yml. As variaveis continuam aceitas para compatibilidade.
CANAL = re.sub(r"[^a-z0-9_-]", "", os.environ.get("CANAL", "").lower())
MODO = os.environ.get("VIDEOBOT_MODO", "gerar").strip().lower()
DRIVE_URL = os.environ.get("DRIVE_URL", "").strip()
DRIVE_CREDENTIALS_FILE = os.environ.get("DRIVE_CREDENTIALS_FILE", "").strip()

# Nichos que ESTE canal usa. Vazio = todos.
NICHOS_CANAL = [n.strip().lower()
                for n in os.environ.get("NICHOS", "").split(",") if n.strip()]

TEMAS = os.path.join(BASE, "temas.txt")     # a pauta e compartilhada
DADOS = os.environ.get("VIDEOBOT_DATA_DIR", os.path.join(BASE, "dados"))
if CANAL:
    PASTA_CANAL = os.path.join(DADOS, CANAL)
    os.makedirs(PASTA_CANAL, exist_ok=True)
    USADOS = os.path.join(PASTA_CANAL, "usados.txt")
    DRIVE_USADOS = os.path.join(PASTA_CANAL, "drive_usados.txt")
    HISTORICO = os.path.join(PASTA_CANAL, "historico.jsonl")
else:
    USADOS = os.path.join(BASE, "usados.txt")
    DRIVE_USADOS = os.path.join(BASE, "drive_usados.txt")
    HISTORICO = os.path.join(BASE, "historico.jsonl")
DOWNLOAD_DRIVE = os.path.join(PASTA_CANAL if CANAL else BASE, "downloads")

# ------------------------------------------------------------- narracao
# Vai como "--video-script-prompt": o MoneyPrinterTurbo anexa isto ao
# prompt padrao dele, sem substituir as regras de formato. Trocar o
# system prompt inteiro quebraria o parsing da resposta.
ESTILO_PADRAO = (
    "Escreva como locutor de video curto, falando direto com quem assiste. "
    "Primeira frase e o gancho: comece pelo fato mais surpreendente, nunca "
    "por apresentacao. Depois explique o porque, em ordem, uma ideia por "
    "frase. Frases curtas. Nada de 'voce sabia', 'neste video' ou "
    "'inscreva-se'. Termine com a informacao mais forte, sem pedir nada."
)

ESTILOS = {
    "dorama": (
        "Escreva como locutor que resume e explica, no tom de quem esta "
        "contando a historia para alguem que nunca viu. Apresente o "
        "conflito, explique por que aquilo funciona com o publico, e "
        "entregue o detalhe de bastidor no fim. Nao invente nome de ator, "
        "de personagem, de titulo nem numero de audiencia: se nao souber "
        "com certeza, fale do padrao e do formato, nunca de uma obra "
        "especifica."
    ),
    "anime": (
        "Escreva como locutor que explica, sem jargao de fa. Assuma que "
        "quem assiste nao acompanha anime. Nao invente nome de estudio, "
        "de obra ou de data: se nao tiver certeza, fale do padrao."
    ),
}

# ---------------------------------------------------------- fonte de imagem
# MIDIA: pasta com filmagem PROPRIA ou devidamente licenciada. Se existir
# material aqui, ele tem prioridade sobre banco de imagem - a cena passa a
# ser sua e some a cara de "video de banco de imagem".
#   midia/<nicho>/*.mp4  -> usada so naquele nicho
#   midia/*.mp4          -> usada em qualquer nicho
# So entra aqui arquivo que voce tem direito de usar. Clipe de filme, serie,
# anime ou podcast alheio e identificado pelo Content ID no upload.
MIDIA = os.path.join(BASE, "midia")
CATALOGO = os.path.join(BASE, "midia.txt")
TMP_MIDIA = os.path.join(BASE, "midia_tmp")
EXT_VIDEO = (".mp4", ".mov", ".mkv", ".webm")
MAX_BAIXAR = 8            # quantos clipes por video
MAX_MB_CLIPE = 120        # ignora arquivo gigante, que so atrasa a execucao

# Bancos de imagem, em ordem de preferencia. O workflow so habilita os que
# tem chave cadastrada. Rodar em mais de um evita repetir o mesmo clipe.
FONTES = [f for f in os.environ.get("FONTES", "pexels").split(",") if f.strip()]

# So publica nas plataformas pedidas para este perfil. Antes o script tentava
# todas em toda execucao, o que confundia falta de credencial com falha.
PLATAFORMAS = {
    p.strip().lower()
    for p in os.environ.get("PLATAFORMAS", "youtube,instagram,tiktok").split(",")
    if p.strip()
}

TESTE = "--teste" in sys.argv
VOZ = "pt-BR-ThalitaMultilingualNeural-Female"
RITMO = "1.18"
MAX_MB = 95  # limite pratico para nao esbarrar em limite de plataforma


def agora():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")


def log(msg):
    print(f"[{agora()}] {msg}", flush=True)


# ------------------------------------------------------------------ tema do dia
def proximo_tema():
    if not os.path.exists(TEMAS):
        sys.exit(f"Sem {TEMAS}")

    usados = set()
    if os.path.exists(USADOS):
        with open(USADOS, encoding="utf-8") as f:
            usados = {l.strip() for l in f if l.strip()}

    linhas = []
    with open(TEMAS, encoding="utf-8") as f:
        for l in f:
            l = l.strip()
            if not l or l.startswith("#") or "|" not in l:
                continue
            linhas.append(l)

    if NICHOS_CANAL:
        do_canal = [l for l in linhas
                    if l.split("|")[0].strip().lower() in NICHOS_CANAL]
        if do_canal:
            linhas = do_canal
        else:
            log(f"nenhum tema nos nichos {NICHOS_CANAL}; usando a lista toda")

    disponiveis = [l for l in linhas if l.split("|")[1].strip() not in usados]

    if not disponiveis:
        log("Todos os temas ja rodaram. Zerando a lista e recomecando.")
        with open(USADOS, "w"):
            pass
        disponiveis = linhas

    return random.choice(disponiveis)


def marcar_usado(tema):
    with open(USADOS, "a", encoding="utf-8") as f:
        f.write(tema + "\n")


# ------------------------------------------------------------ midia propria
def midia_local(nicho):
    """Devolve lista de arquivos proprios para o nicho, ou [] se nao houver."""
    if not os.path.isdir(MIDIA):
        return []
    pastas = [os.path.join(MIDIA, nicho.replace(" ", "-")), MIDIA]
    for pasta in pastas:
        if not os.path.isdir(pasta):
            continue
        arqs = sorted(
            os.path.join(pasta, f) for f in os.listdir(pasta)
            if f.lower().endswith(EXT_VIDEO)
        )
        if arqs:
            random.shuffle(arqs)
            return arqs[:12]   # o MPT nao precisa de mais que isso por video
    return []


def _catalogo(nicho):
    """Linhas nicho|url do catalogo, com as marcadas * valendo para todos."""
    if not os.path.exists(CATALOGO):
        return []
    do_nicho, gerais = [], []
    with open(CATALOGO, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "|" not in linha:
                continue
            alvo, url = linha.split("|", 1)
            url = url.strip()
            if not url.lower().startswith(("http://", "https://")):
                continue
            alvo = alvo.strip().lower()
            if alvo == nicho.lower():
                do_nicho.append(url)
            elif alvo == "*":
                gerais.append(url)
    return do_nicho or gerais


def baixar_midia(nicho):
    """Baixa so os clipes que este video vai usar. Falha de um nao derruba."""
    urls = _catalogo(nicho)
    if not urls:
        return []

    import urllib.request
    random.shuffle(urls)
    os.makedirs(TMP_MIDIA, exist_ok=True)
    baixados = []

    for i, url in enumerate(urls[:MAX_BAIXAR]):
        destino = os.path.join(TMP_MIDIA, f"clipe{i}.mp4")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "videobot"})
            with urllib.request.urlopen(req, timeout=120) as r:
                tamanho = int(r.headers.get("Content-Length") or 0)
                if tamanho and tamanho > MAX_MB_CLIPE * 1024 * 1024:
                    log(f"  pulando clipe de {tamanho // 1048576} MB")
                    continue
                dados = r.read(MAX_MB_CLIPE * 1024 * 1024 + 1)
            if len(dados) > MAX_MB_CLIPE * 1024 * 1024:
                log("  pulando clipe grande demais")
                continue
            # Se veio HTML e porque a URL abre uma pagina, nao o arquivo.
            if dados[:15].lstrip()[:9].lower().startswith(b"<!doctype") or \
               dados[:6].lower().startswith(b"<html"):
                log("  a URL devolveu pagina, nao arquivo: confira o link direto")
                continue
            with open(destino, "wb") as f:
                f.write(dados)
            baixados.append(destino)
        except (OSError, ValueError) as e:
            log(f"  falhou baixar clipe: {type(e).__name__}")

    if baixados:
        log(f"catalogo: {len(baixados)} clipes baixados de {len(urls)} no nicho")
    return baixados


def escolher_fonte(nicho):
    """(video_source, lista_de_arquivos). Local ganha de banco de imagem."""
    arqs = midia_local(nicho)
    if arqs:
        log(f"usando midia propria da pasta: {len(arqs)} arquivos")
        return "local", arqs

    arqs = baixar_midia(nicho)
    if arqs:
        log(f"usando midia propria do catalogo: {len(arqs)} arquivos")
        return "local", arqs

    fonte = random.choice(FONTES) if FONTES else "pexels"
    log(f"usando banco de imagem: {fonte}")
    return fonte, []


# --------------------------------------------------------------------- geracao
def gerar(tema, termos, estilo="", fonte="pexels", arquivos=None):
    task_id = str(uuid.uuid4())
    cmd = [
        VENV_PY, "cli.py",
        "--video-subject", tema,
        "--video-language", "pt-BR",
        "--video-source", fonte,
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
        "--video-script-prompt", (estilo or ESTILO_PADRAO),
        "--n-threads", str(max(2, os.cpu_count() or 2)),
        "--task-id", task_id,
    ]

    # Com material local o MPT nao busca nada, entao termo de busca nao se
    # aplica: passar os dois junto e erro de argumento.
    if fonte == "local" and arquivos:
        cmd += ["--video-materials", ",".join(arquivos)]
    else:
        cmd += ["--video-terms", termos]

    env = dict(os.environ)
    env["SSL_CERT_FILE"] = "/etc/ssl/certs/ca-certificates.crt"
    env["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"

    log(f"Gerando: {tema}")
    try:
        r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True,
                           text=True, timeout=60 * 20, check=False)
    except subprocess.TimeoutExpired:
        log("FALHOU: a geracao passou de 20 min e foi cortada.")
        return None, None

    saida = os.path.join(REPO, "storage", "tasks", task_id, "final-1.mp4")
    if r.returncode != 0 or not os.path.exists(saida):
        tudo = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        erros = [l for l in tudo.splitlines() if "ERROR" in l or "error=" in l]
        log("FALHOU na geracao.")
        for l in (erros or tudo.splitlines())[-5:]:
            log("   " + re.sub(r"\x1b\[[0-9;]*m", "", l)[:260])
        baixo = tudo.lower()
        if ("api key" in baixo or "api_key" in baixo or "401" in baixo
                or "invalid_argument" in baixo or "permission_denied" in baixo):
            log("   >> parece falta de chave de LLM. Pegue uma gratis em")
            log("      aistudio.google.com/apikey e ponha gemini_api_key no config.toml")
        return None, None

    # roteiro, para usar na descricao
    roteiro = ""
    js = os.path.join(REPO, "storage", "tasks", task_id, "script.json")
    if os.path.exists(js):
        try:
            with open(js, encoding="utf-8") as f:
                roteiro = json.load(f).get("script", "") or ""
        except (OSError, json.JSONDecodeError) as e:
            log(f"nao foi possivel ler o roteiro salvo: {e}")

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
    except ImportError as e:
        log(f"youtube_post indisponivel: {e}")
        return None

    if not os.path.exists(youtube_post.TOKEN_FILE):
        log(f"Sem token do YouTube para o canal {CANAL or 'unico'}. Pulando.")
        return None

    desc = (roteiro.strip()[:900] + "\n\n#shorts " +
            " ".join("#" + t.strip().replace(" ", "") for t in tags.split(",")[:5]))
    try:
        return youtube_post.cmd_upload(caminho, titulo_de(tema), desc, tags, "public")
    except SystemExit as e:
        log(f"YouTube falhou: {e}")
    except Exception as e:  # noqa: BLE001 - fronteira com SDK externo
        log(f"YouTube falhou: {e}")
    return None


def postar_instagram(caminho, tema, roteiro):
    """Publica Reels de verdade. Pula em silencio se nao estiver configurado.

    O Instagram nao recebe arquivo: exige URL publica e busca o video de la.
    Por isso o mp4 sobe antes para um Release do repositorio.
    """
    if not (os.environ.get("IG_USER_ID") and os.environ.get("IG_TOKEN")):
        return None
    try:
        sys.path.insert(0, BASE)
        import instagram_post
        import publicar_release

        url = publicar_release.subir(caminho, tag="videos")
        legenda = tema
        if roteiro:
            legenda += "\n\n" + roteiro.strip()[:1500]
        return instagram_post.cmd_publicar(url, legenda)
    except SystemExit as e:
        log(f"Instagram nao publicou: {e}")
    except Exception as e:  # noqa: BLE001 - fronteira com API externa
        log(f"Instagram falhou ({type(e).__name__}: {e})")
    return None


def postar_tiktok(caminho, tema, tags):
    sys.path.insert(0, BASE)
    try:
        import tiktok_post
        if not os.path.exists(tiktok_post.TOKEN_FILE):
            log(f"Sem token do TikTok para o canal {CANAL or 'unico'}. Pulando.")
            return False
        legenda = titulo_de(tema) + " " + " ".join(
            "#" + t.strip().replace(" ", "") for t in tags.split(",")[:5]
        )
        return tiktok_post.cmd_upload(caminho, legenda=legenda)
    except SystemExit as e:
        log(f"TikTok falhou: {e}")
    except Exception as e:  # noqa: BLE001 - fronteira com API externa
        log(f"TikTok falhou: {e}")
    return False


# ------------------------------------------------------------------------ main
def atualizar_temas():
    """Busca tema novo em cima do que esta em alta. Nunca derruba a execucao:
    se falhar, o temas.txt que ja esta no repositorio continua valendo."""
    if os.environ.get("ATUALIZAR_TEMAS", "1") == "0":
        return
    try:
        import temas_auto
        temas_auto.atualizar()
    except Exception as e:  # noqa: BLE001 - renovacao nao pode derrubar o video
        log(f"atualizacao de temas falhou ({type(e).__name__}: {e}). "
            f"Seguindo com a lista atual.")


def main():
    log("=" * 55)
    if CANAL:
        log(f"canal: {CANAL} | nichos: {', '.join(NICHOS_CANAL) or 'todos'}")
    origem_drive_id = ""
    if MODO == "drive":
        if not DRIVE_URL:
            sys.exit("Canal em modo drive sem DRIVE_URL.")
        try:
            import drive_source

            item_drive, caminho_drive = drive_source.escolher_e_baixar(
                DRIVE_URL,
                Path(DOWNLOAD_DRIVE),
                Path(DRIVE_USADOS),
                DRIVE_CREDENTIALS_FILE,
            )
        except drive_source.ErroDrive as e:
            log(f"Drive falhou: {e}")
            return 1
        origem_drive_id = item_drive.id
        caminho = str(caminho_drive)
        nicho = NICHOS_CANAL[0] if NICHOS_CANAL else (CANAL or "video")
        tema = Path(item_drive.nome).stem
        roteiro = ""
        log(f"Drive: {item_drive.caminho or item_drive.nome}")
    else:
        atualizar_temas()
        linha = proximo_tema()
        partes = [p.strip() for p in linha.split("|")]
        nicho, tema, termos = (partes + ["", "", ""])[:3]
    tags = {"mar": "oceano,ciencia,curiosidades",
            "dinheiro": "financas,dinheiro,economia",
            "espiritual": "misterio,historia,curiosidades",
            "anime": "anime,otaku,curiosidades",
            "dorama": "dorama,novela chinesa,cdrama",
            "tecnologia": "tecnologia,ciencia,curiosidades",
            "historia": "historia,curiosidades,cultura",
            "espaco": "espaco,astronomia,ciencia",
            "corpo humano": "corpo humano,saude,ciencia",
            "misterio": "misterio,curiosidades,enigma",
            }.get(nicho, f"{nicho},curiosidades,shorts" if nicho else "curiosidades")

    if MODO != "drive":
        estilo = ESTILOS.get(nicho, ESTILO_PADRAO)
        fonte, arquivos = escolher_fonte(nicho)
        caminho, roteiro = gerar(tema, termos, estilo, fonte, arquivos)
        if not caminho:
            sys.exit(1)

    if TESTE:
        log(f"MODO TESTE. Video em {caminho}. Nada foi postado.")
        return

    resultados = {}
    if "youtube" in PLATAFORMAS:
        resultados["youtube"] = postar_youtube(caminho, tema, roteiro, tags)
    if "instagram" in PLATAFORMAS:
        resultados["instagram"] = postar_instagram(caminho, tema, roteiro)
    if "tiktok" in PLATAFORMAS:
        chave_tiktok = (
            "tiktok" if os.environ.get("TIKTOK_DIRECT_POST") == "1"
            else "tiktok_rascunho"
        )
        resultados[chave_tiktok] = postar_tiktok(caminho, tema, tags)

    houve_publicacao = any(bool(valor) for valor in resultados.values())
    if houve_publicacao:
        if origem_drive_id:
            import drive_source

            drive_source.marcar_usado(Path(DRIVE_USADOS), origem_drive_id)
        else:
            marcar_usado(tema)

    with open(HISTORICO, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "quando": agora(), "canal": CANAL or "unico",
            "nicho": nicho, "tema": tema,
            "arquivo": caminho,
            "drive_file_id": origem_drive_id or None,
            "plataformas_solicitadas": sorted(PLATAFORMAS),
            "resultados": resultados,
            "publicou": houve_publicacao,
        }, ensure_ascii=False) + "\n")

    log(f"Fim. resultados={resultados}")
    if not houve_publicacao:
        log("Nenhuma plataforma publicou. O tema nao foi marcado como usado.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
