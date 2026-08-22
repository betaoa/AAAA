#!/data/data/com.termux/files/usr/bin/bash
# Instala uma unica central multicanal no Termux. Canais, nichos, horarios e
# plataformas ficam em config/canais.yml; nao existe mais um loop por nicho.
set -e

echo ">> pacotes do sistema"
pkg update -y
pkg install -y python ffmpeg git rust binutils termux-api
pkg install -y python-numpy python-pillow || true

echo ">> dependencias Python"
export CARGO_BUILD_JOBS=2
export IMAGEIO_FFMPEG_EXE="$(command -v ffmpeg)"
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.exemplo .env
  echo
  echo "Criei .env. Preencha as chaves sem colar nenhuma delas no chat."
  echo "Depois rode novamente: bash instalar-termux.sh"
  exit 0
fi

set -a
. ./.env
set +a

PRECISA_GERAR="$(python - <<'PY'
import yaml
d = yaml.safe_load(open("config/canais.yml", encoding="utf-8")) or {}
p = (d.get("padroes") or {}).get("modo", "gerar")
print("1" if any((c.get("modo") or p) == "gerar" for c in d.get("canais", [])) else "0")
PY
)"

if [ "$PRECISA_GERAR" = "1" ]; then
echo ">> renderizador"
if [ ! -d MoneyPrinterTurbo ]; then
  REF="${MPT_REF:-5dde46390809edba44c2e8d09760623bb846fd9d}"
  git init MoneyPrinterTurbo
  git -C MoneyPrinterTurbo remote add origin https://github.com/harry0703/MoneyPrinterTurbo.git
  git -C MoneyPrinterTurbo fetch --depth 1 origin "$REF"
  git -C MoneyPrinterTurbo checkout --detach FETCH_HEAD
fi
cp -n MoneyPrinterTurbo/config.example.toml MoneyPrinterTurbo/config.toml

python - <<'PY'
import os, re, sys
p = "MoneyPrinterTurbo/config.toml"
s = open(p, encoding="utf-8").read()

def setar(chave, valor, texto):
    padrao = rf'^{re.escape(chave)}\s*=.*$'
    if not re.search(padrao, texto, flags=re.M):
        sys.exit(f"chave '{chave}' nao existe no config do MoneyPrinterTurbo")
    return re.sub(padrao, f'{chave} = {valor}', texto, count=1, flags=re.M)

gem = os.environ.get("GEMINI_KEY", "")
pex = os.environ.get("PEXELS_KEY", "")
if not gem or not pex:
    sys.exit("Preencha GEMINI_KEY e PEXELS_KEY no .env")
s = setar("video_source", '"pexels"', s)
s = setar("subtitle_provider", '"edge"', s)
s = setar("llm_provider", '"gemini"', s)
s = setar("gemini_api_key", f'"{gem}"', s)
s = setar("gemini_model_name", f'"{os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"}"', s)
s = setar("pexels_api_keys", f'["{pex}"]', s)
fontes = ["pexels"]
if os.environ.get("PIXABAY_KEY"):
    s = setar("pixabay_api_keys", f'["{os.environ["PIXABAY_KEY"]}"]', s)
    fontes.append("pixabay")
if os.environ.get("COVERR_KEY"):
    s = setar("coverr_api_keys", f'["{os.environ["COVERR_KEY"]}"]', s)
    fontes.append("coverr")
open(p, "w", encoding="utf-8").write(s)
with open(".fontes", "w", encoding="utf-8") as f:
    f.write(",".join(fontes))
print("configuracao do renderizador pronta")
PY
else
  echo ">> modo Drive: renderizador e chaves Gemini/Pexels nao sao necessarios"
fi

chmod +x iniciar-termux.sh
python videobot.py validar

echo
echo "INSTALACAO PRONTA."
echo "Teste:             python videobot.py rodar --canal limpeza --teste"
echo "Deixar 24 horas:   ./iniciar-termux.sh"
