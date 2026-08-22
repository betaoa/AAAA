#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"
set -a
. ./.env
set +a
export FONTES="$(cat .fontes 2>/dev/null || echo pexels)"
export IMAGEIO_FFMPEG_EXE="$(command -v ffmpeg)"
termux-wake-lock || true
mkdir -p dados

if [ "${1:-}" = "--frente" ]; then
  exec python videobot.py daemon
fi

nohup python videobot.py daemon >> dados/daemon.log 2>&1 &
echo $! > dados/daemon.pid
echo "Videobot iniciado em segundo plano. PID $(cat dados/daemon.pid)"
echo "Acompanhar: tail -f dados/daemon.log"

