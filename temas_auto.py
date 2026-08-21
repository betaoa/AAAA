#!/usr/bin/env python3
"""
temas_auto.py - mantem temas.txt vivo, alimentado por tendencia real.

O problema que este arquivo resolve: o Gemini nao navega na internet por
conta propria. Se voce simplesmente pedir "temas em alta hoje", ele
responde do que aprendeu no treino e inventa tendencia plausivel. Para
o tema ser de verdade, alguem precisa entregar dado fresco a ele.

Fluxo, e o que acontece quando cada etapa falha:

  1. Puxa os videos mais populares do YouTube (Brasil e Estados Unidos)
     pela Data API. Isso e sinal real, custa 1 unidade de cota por
     chamada, de 10.000 por dia. Sem YOUTUBE_API_KEY, pula e segue.

  2. Manda esses titulos ao Gemini com a busca do Google ligada, quando
     a cota permitir, e pede temas novos no formato do bot. Se o
     grounding nao estiver liberado, refaz sem ele: pior, mas funciona.

  3. Valida linha por linha e descarta o que ja esta em usados.txt.

  4. Reescreve temas.txt. Se qualquer etapa falhar, o arquivo antigo
     fica intacto - o bot nunca fica sem tema.

Rodar sozinho para testar:
    GEMINI_KEY=xxx YOUTUBE_API_KEY=yyy python3 temas_auto.py
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
TEMAS = os.path.join(BASE, "temas.txt")
USADOS = os.path.join(BASE, "usados.txt")

MODELO = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
REGIOES = ["BR", "US"]
ALVO = int(os.environ.get("TEMAS_ALVO", "60"))   # tamanho da lista mantida
TETO = 200                                       # nunca deixa passar disso

# Nichos que o canal ja tem. O Gemini pode criar outros: a lista e
# sugestao, nao camisa de forca. Foi isso que voce pediu com "infinitos".
NICHOS = ["mar", "dinheiro", "espiritual", "anime", "tecnologia",
          "historia", "espaco", "corpo humano", "misterio"]

LINHA_OK = re.compile(r"^[a-z0-9 \-]{3,20}\|[^|]{15,110}\|[^|]{10,160}$")


def log(msg):
    print(f"[temas_auto] {msg}", flush=True)


# ------------------------------------------------------------------ arquivos
def _ler(caminho):
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8") as f:
        return [l.rstrip("\n") for l in f]


def _temas_atuais():
    """Devolve (comentarios, linhas validas)."""
    comentarios, linhas = [], []
    for l in _ler(TEMAS):
        s = l.strip()
        if not s:
            continue
        if s.startswith("#"):
            comentarios.append(s)
        elif s.count("|") == 2:
            linhas.append(s)
    return comentarios, linhas


def _usados():
    return {l.strip() for l in _ler(USADOS) if l.strip()}


# -------------------------------------------------------------- tendencia real
def tendencias_youtube(chave):
    """Titulos em alta agora. Fato, nao palpite. 1 unidade de cota por regiao."""
    if not chave:
        log("sem YOUTUBE_API_KEY: seguindo sem os titulos em alta")
        return []

    titulos = []
    for regiao in REGIOES:
        params = urllib.parse.urlencode({
            "part": "snippet",
            "chart": "mostPopular",
            "regionCode": regiao,
            "maxResults": "30",
            "key": chave,
        })
        url = "https://www.googleapis.com/youtube/v3/videos?" + params
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                dados = json.load(r)
            novos = [i["snippet"]["title"] for i in dados.get("items", [])]
            titulos += novos
            log(f"{regiao}: {len(novos)} titulos em alta")
        except Exception as e:
            log(f"{regiao}: falhou ({type(e).__name__}: {e})")
    return titulos


# ------------------------------------------------------------------ o pedido
def _prompt(titulos, usados, quantos):
    bloco_alta = ""
    if titulos:
        amostra = "\n".join("- " + t for t in titulos[:50])
        bloco_alta = (
            "Estes sao titulos que estao no topo do YouTube AGORA, "
            "no Brasil e nos Estados Unidos. Use como termometro do que "
            "prende atencao neste momento - formato, gancho, assunto:\n"
            f"{amostra}\n\n"
        )

    bloco_usados = ""
    if usados:
        amostra = "\n".join("- " + t for t in sorted(usados)[-80:])
        bloco_usados = (
            "NAO repita nem parafraseie nenhum destes, que ja foram usados:\n"
            f"{amostra}\n\n"
        )

    return (
        "Voce monta a pauta de um canal brasileiro de Shorts de "
        "curiosidades chamado 'Sabia Disso?'.\n\n"
        f"{bloco_alta}{bloco_usados}"
        f"Escreva {quantos} temas novos, um por linha, EXATAMENTE neste "
        "formato de tres campos separados por barra vertical:\n\n"
        "nicho|tema|termos de busca em ingles separados por virgula\n\n"
        "Regras:\n"
        f"- nicho: uma palavra curta em minusculas. Use estes quando "
        f"couber: {', '.join(NICHOS)}. Pode criar outros se o assunto pedir.\n"
        "- tema: uma afirmacao ou pergunta curiosa em portugues do Brasil, "
        "entre 25 e 100 caracteres, que caiba num video de 40 segundos. "
        "Sem emoji, sem aspas, sem numeracao.\n"
        "- termos: 4 a 6 termos de busca de banco de imagens, em INGLES, "
        "separados por virgula. Precisam existir como filmagem real no "
        "Pexels. Concreto e visual: 'deep sea, bioluminescence' funciona, "
        "'existential doubt' nao.\n"
        "- Misture assunto atemporal com assunto puxado do que esta em "
        "alta agora.\n"
        "- Nada de politica, tragedia recente, doenca, crime ou pessoa "
        "real viva citada pelo nome.\n\n"
        "Responda SOMENTE com as linhas. Sem titulo, sem explicacao, "
        "sem marcacao de codigo."
    )


def pedir_ao_gemini(chave, titulos, usados, quantos):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log("SDK google-genai ausente: nao da para gerar tema novo")
        return []

    cliente = genai.Client(api_key=chave)
    prompt = _prompt(titulos, usados, quantos)

    # Primeiro com a busca do Google ligada. Se a cota gratuita nao
    # cobrir grounding, o SDK levanta erro e a gente refaz sem.
    tentativas = [
        ("com busca do Google", types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=1.1,
        )),
        ("sem busca", types.GenerateContentConfig(temperature=1.1)),
    ]

    for rotulo, config in tentativas:
        try:
            resp = cliente.models.generate_content(
                model=MODELO, contents=prompt, config=config)
            texto = (resp.text or "").strip()
            if texto:
                log(f"Gemini respondeu {rotulo}")
                return texto.splitlines()
            log(f"Gemini devolveu vazio {rotulo}")
        except Exception as e:
            log(f"Gemini falhou {rotulo}: {type(e).__name__}: {e}")
    return []


# ------------------------------------------------------------------ validacao
def validar(linhas, usados, ja_tem):
    """So passa linha no formato certo, inedita, e com termos em ingles."""
    vistos = {l.split("|")[1].strip().lower() for l in ja_tem}
    vistos |= {t.lower() for t in usados}
    bons = []

    for bruta in linhas:
        l = bruta.strip().strip("`").lstrip("-*0123456789. ").strip()
        if not l or l.count("|") != 2:
            continue
        nicho, tema, termos = [p.strip() for p in l.split("|")]
        linha = f"{nicho.lower()}|{tema}|{termos.lower()}"
        if not LINHA_OK.match(linha):
            continue
        if tema.lower() in vistos:
            continue
        # termos precisam ser ascii: acento aqui significa portugues,
        # e o acervo do Pexels em portugues e pobre.
        if not termos.isascii():
            continue
        vistos.add(tema.lower())
        bons.append(linha)

    return bons


# ------------------------------------------------------------------ orquestra
def atualizar(alvo=ALVO):
    chave_gemini = os.environ.get("GEMINI_KEY", "")
    chave_youtube = os.environ.get("YOUTUBE_API_KEY", "")

    comentarios, atuais = _temas_atuais()
    usados = _usados()
    disponiveis = [l for l in atuais if l.split("|")[1].strip() not in usados]
    log(f"lista atual: {len(atuais)} temas, {len(disponiveis)} ainda nao usados")

    if not chave_gemini:
        log("sem GEMINI_KEY: mantendo a lista como esta")
        return False

    faltam = max(alvo - len(disponiveis), 12)
    titulos = tendencias_youtube(chave_youtube)
    brutas = pedir_ao_gemini(chave_gemini, titulos, usados, faltam)
    novas = validar(brutas, usados, atuais)

    if not novas:
        log("nenhum tema novo aproveitavel: lista antiga preservada")
        return False

    log(f"{len(novas)} temas novos aprovados de {len(brutas)} linhas recebidas")

    # novos primeiro, e corta a cauda velha para o arquivo nao crescer sem fim
    final = novas + atuais
    final = final[:TETO]

    # Separadores de secao viram lixo assim que a lista passa a ser
    # automatica: mantem so a linha que explica o formato.
    cabecalho = [c for c in comentarios
                 if "|" in c and not c.startswith("# atualizado")][:1]
    if not cabecalho:
        cabecalho = ["# nicho|tema|termos de busca no Pexels (em ingles)"]
    cabecalho.append(
        f"# atualizado automaticamente por temas_auto.py "
        f"({len(novas)} novos, {len(titulos)} titulos em alta consultados)")

    with open(TEMAS, "w", encoding="utf-8") as f:
        f.write("\n".join(cabecalho + final) + "\n")

    log(f"temas.txt reescrito com {len(final)} linhas")
    return True


if __name__ == "__main__":
    atualizar()
