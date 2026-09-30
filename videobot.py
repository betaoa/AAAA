#!/usr/bin/env python3
"""Central de execucao do videobot.

Comandos mais usados:
    python videobot.py validar
    python videobot.py listar
    python videobot.py rodar --canal sabiadisso --teste
    python videobot.py daemon

O mesmo arquivo funciona no PC, Termux e GitHub Actions. A configuracao de
canais fica em config/canais.yml; nao e mais necessario duplicar repositorio
nem editar o workflow para acrescentar um canal.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import yaml
except ImportError:  # mensagem mais util que um traceback
    yaml = None


BASE = Path(__file__).resolve().parent
CONFIG_PADRAO = BASE / "config" / "canais.yml"
DADOS = BASE / "dados"
PLATAFORMAS_VALIDAS = {"youtube", "instagram", "tiktok"}
MODOS_VALIDOS = {"gerar", "drive"}
ID_OK = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")


class ErroConfig(ValueError):
    pass


@dataclass(frozen=True)
class Canal:
    id: str
    nome: str
    ativo: bool
    nichos: tuple[str, ...]
    plataformas: tuple[str, ...]
    horarios: tuple[str, ...]
    fuso: str
    modo: str
    drive_url: str


@dataclass(frozen=True)
class Config:
    canais: tuple[Canal, ...]
    fuso: str
    tolerancia_minutos: int
    intervalo_daemon_segundos: int
    max_paralelo: int


def _carregar_yaml(caminho: Path) -> dict:
    if yaml is None:
        raise ErroConfig("Falta PyYAML. Rode: pip install -r requirements.txt")
    if not caminho.is_file():
        raise ErroConfig(f"Configuracao nao encontrada: {caminho}")
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ErroConfig(f"YAML invalido em {caminho}: {exc}") from None
    if not isinstance(dados, dict):
        raise ErroConfig("A raiz de config/canais.yml precisa ser um objeto.")
    return dados


def _horario(valor: object, canal: str) -> str:
    texto = str(valor).strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", texto):
        raise ErroConfig(f"Canal {canal}: horario invalido '{texto}'. Use HH:MM.")
    return texto


def carregar_config(caminho: Path = CONFIG_PADRAO) -> Config:
    bruto = _carregar_yaml(caminho)
    padroes = bruto.get("padroes") or {}
    if not isinstance(padroes, dict):
        raise ErroConfig("'padroes' precisa ser um objeto.")

    fuso_padrao = str(padroes.get("fuso") or "America/Cuiaba")
    try:
        ZoneInfo(fuso_padrao)
    except ZoneInfoNotFoundError:
        raise ErroConfig(f"Fuso desconhecido: {fuso_padrao}") from None

    canais_brutos = bruto.get("canais")
    if not isinstance(canais_brutos, list) or not canais_brutos:
        raise ErroConfig("Cadastre pelo menos um canal em 'canais'.")

    canais: list[Canal] = []
    ids: set[str] = set()
    for item in canais_brutos:
        if not isinstance(item, dict):
            raise ErroConfig("Cada item de 'canais' precisa ser um objeto.")
        cid = str(item.get("id") or "").strip().lower()
        if not ID_OK.fullmatch(cid):
            raise ErroConfig(
                f"ID de canal invalido '{cid}'. Use letras minusculas, numeros, _ ou -."
            )
        if cid in ids:
            raise ErroConfig(f"ID de canal repetido: {cid}")
        ids.add(cid)

        nichos = tuple(dict.fromkeys(
            str(x).strip().lower() for x in (item.get("nichos") or []) if str(x).strip()
        ))
        plataformas = tuple(dict.fromkeys(
            str(x).strip().lower()
            for x in (item.get("plataformas") or padroes.get("plataformas") or [])
            if str(x).strip()
        ))
        invalidas = set(plataformas) - PLATAFORMAS_VALIDAS
        if invalidas:
            raise ErroConfig(f"Canal {cid}: plataformas invalidas: {sorted(invalidas)}")
        if not plataformas:
            raise ErroConfig(f"Canal {cid}: informe ao menos uma plataforma.")

        fuso = str(item.get("fuso") or fuso_padrao)
        try:
            ZoneInfo(fuso)
        except ZoneInfoNotFoundError:
            raise ErroConfig(f"Canal {cid}: fuso desconhecido '{fuso}'.") from None

        horarios = tuple(dict.fromkeys(
            _horario(x, cid)
            for x in (item.get("horarios") or padroes.get("horarios") or [])
        ))
        modo = str(item.get("modo") or padroes.get("modo") or "gerar").lower()
        if modo not in MODOS_VALIDOS:
            raise ErroConfig(f"Canal {cid}: modo invalido '{modo}'.")
        drive_url = str(item.get("drive_url") or "").strip()
        if modo == "drive" and not drive_url:
            raise ErroConfig(f"Canal {cid}: modo drive exige drive_url.")
        canais.append(Canal(
            id=cid,
            nome=str(item.get("nome") or cid),
            ativo=bool(item.get("ativo", True)),
            nichos=nichos,
            plataformas=plataformas,
            horarios=horarios,
            fuso=fuso,
            modo=modo,
            drive_url=drive_url,
        ))

    def inteiro(nome: str, padrao: int, minimo: int, maximo: int) -> int:
        try:
            valor = int(padroes.get(nome, padrao))
        except (TypeError, ValueError):
            raise ErroConfig(f"padroes.{nome} precisa ser numero inteiro.") from None
        if not minimo <= valor <= maximo:
            raise ErroConfig(f"padroes.{nome} precisa ficar entre {minimo} e {maximo}.")
        return valor

    return Config(
        canais=tuple(canais),
        fuso=fuso_padrao,
        tolerancia_minutos=inteiro("tolerancia_minutos", 35, 1, 180),
        intervalo_daemon_segundos=inteiro("intervalo_daemon_segundos", 30, 10, 3600),
        max_paralelo=inteiro("max_paralelo", 1, 1, 8),
    )


def obter_canal(config: Config, canal_id: str) -> Canal:
    for canal in config.canais:
        if canal.id == canal_id:
            return canal
    raise ErroConfig(f"Canal '{canal_id}' nao existe em config/canais.yml.")


def _sufixo(canal_id: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", canal_id.upper())


def _pasta_canal(canal: Canal) -> Path:
    pasta = DADOS / canal.id
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _estado(canal: Canal) -> dict:
    caminho = _pasta_canal(canal) / "agenda.json"
    if not caminho.is_file():
        return {"slots": {}}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {"slots": {}}
    except (OSError, json.JSONDecodeError):
        return {"slots": {}}


def _salvar_estado(canal: Canal, estado: dict) -> None:
    caminho = _pasta_canal(canal) / "agenda.json"
    slots = estado.setdefault("slots", {})
    if len(slots) > 60:
        for antigo in sorted(slots)[:-60]:
            slots.pop(antigo, None)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporario, caminho)


@contextlib.contextmanager
def trava(canal: Canal) -> Iterator[bool]:
    caminho = _pasta_canal(canal) / ".executando.lock"
    try:
        fd = os.open(str(caminho), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            idade = time.time() - caminho.stat().st_mtime
            if idade > 45 * 60:
                caminho.unlink(missing_ok=True)
                fd = os.open(str(caminho), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            else:
                yield False
                return
        except (FileNotFoundError, FileExistsError):
            yield False
            return
    os.write(
        fd,
        f"pid={os.getpid()} inicio={dt.datetime.now(dt.timezone.utc).isoformat()}".encode(),
    )
    os.close(fd)
    try:
        yield True
    finally:
        caminho.unlink(missing_ok=True)


def _materializar_json_env(nome: str, destino: Path) -> bool:
    conteudo = os.environ.get(nome, "").strip()
    if not conteudo:
        return False
    try:
        json.loads(conteudo)
    except json.JSONDecodeError:
        raise ErroConfig(f"A variavel {nome} nao contem um JSON valido.") from None
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return True


def ambiente_do_canal(canal: Canal) -> dict[str, str]:
    env = dict(os.environ)
    sufixo = _sufixo(canal.id)
    pasta = _pasta_canal(canal)
    env.update({
        "CANAL": canal.id,
        "NICHOS": ",".join(canal.nichos),
        "PLATAFORMAS": ",".join(canal.plataformas),
        "VIDEOBOT_DATA_DIR": str(DADOS),
        "VIDEOBOT_MODO": canal.modo,
        "DRIVE_URL": canal.drive_url,
        "DRIVE_FOLDER_NAME": canal.nome,
    })

    # Uma unica autorizacao do Drive pode ler todas as pastas da central.
    drive_informado = Path(os.environ.get("DRIVE_CREDENTIALS_FILE", ""))
    drive_destino = (
        drive_informado if drive_informado.is_file()
        else DADOS / "drive_credentials.json"
    )
    _materializar_json_env("DRIVE_CREDENTIALS", drive_destino)
    drive_local = BASE / "secrets" / "drive_credentials.json"
    if drive_local.is_file() and not drive_destino.is_file():
        drive_destino = drive_local
    env["DRIVE_CREDENTIALS_FILE"] = str(drive_destino)

    # No GitHub, os tokens chegam como JSON em secret. No PC/Termux, podem
    # ficar em secrets/*.json. Em ambos os casos rodar.py recebe um caminho.
    yt_destino = pasta / "youtube_token.json"
    yt_env = f"YOUTUBE_TOKEN_{sufixo}"
    permite_geral = os.environ.get("VIDEOBOT_PERMITE_CREDENCIAL_GERAL", "1") == "1"
    if not _materializar_json_env(yt_env, yt_destino) and permite_geral:
        _materializar_json_env("YOUTUBE_TOKEN", yt_destino)
    yt_local = BASE / "secrets" / f"youtube-{canal.id}.json"
    if yt_local.is_file() and not yt_destino.is_file():
        yt_destino = yt_local
    env["YOUTUBE_TOKEN_FILE"] = str(yt_destino)

    tk_destino = pasta / "tiktok_tokens.json"
    tk_env = f"TIKTOK_TOKEN_{sufixo}"
    if not _materializar_json_env(tk_env, tk_destino) and permite_geral:
        _materializar_json_env("TIKTOK_TOKEN", tk_destino)
    tk_local = BASE / "secrets" / f"tiktok-{canal.id}.json"
    if tk_local.is_file() and not tk_destino.is_file():
        tk_destino = tk_local
    env["TIKTOK_TOKEN_FILE"] = str(tk_destino)

    # Credenciais simples: aceita o valor especifico do canal e cai no geral.
    for nome in (
        "IG_USER_ID", "IG_TOKEN", "IG_APP_ID", "IG_APP_SECRET",
        "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REDIRECT_URI",
    ):
        especifica = os.environ.get(f"{nome}_{sufixo}")
        if especifica:
            env[nome] = especifica
        elif not permite_geral:
            env.pop(nome, None)
    return env


def executar(
    canal: Canal, teste: bool = False, slot: str = "",
    tema: str = "", termos: str = "",
) -> int:
    with trava(canal) as adquiriu:
        if not adquiriu:
            print(f"[{canal.id}] ja existe uma execucao em andamento; pulando.", flush=True)
            return 3

        estado = _estado(canal)
        if slot and slot != "manual":
            anterior = estado.setdefault("slots", {}).get(slot, {})
            if anterior.get("status") == "ok":
                print(f"[{canal.id}] horario {slot} ja concluido; pulando.", flush=True)
                return 0
            tentativas = int(anterior.get("tentativas", 0)) + 1
            estado["slots"][slot] = {
                "status": "executando",
                "inicio": dt.datetime.now(dt.timezone.utc).isoformat(),
                "tentativas": tentativas,
            }
            _salvar_estado(canal, estado)

        comando = [sys.executable, str(BASE / "rodar.py")]
        if teste:
            comando.append("--teste")
        env = ambiente_do_canal(canal)
        env.pop("VIDEOBOT_TEMA", None)
        env.pop("VIDEOBOT_TERMOS", None)
        if tema:
            # A pauta manual gera um Short nesta execucao, mesmo quando o
            # canal normalmente publica arquivos do Drive.
            env["VIDEOBOT_MODO"] = "gerar"
            env["VIDEOBOT_TEMA"] = tema
            env["VIDEOBOT_TERMOS"] = termos
        print(
            f"[{canal.id}] iniciando | modo={env['VIDEOBOT_MODO']} "
            f"| nichos={','.join(canal.nichos) or 'todos'} "
            f"| plataformas={','.join(canal.plataformas)} | teste={teste}",
            flush=True,
        )
        try:
            resultado = subprocess.run(
                comando, cwd=BASE, env=env, check=False
            )
            codigo = resultado.returncode
        except KeyboardInterrupt:
            codigo = 130

        if slot and slot != "manual":
            estado = _estado(canal)
            anterior = estado.setdefault("slots", {}).get(slot, {})
            estado["slots"][slot] = {
                "status": "ok" if codigo == 0 else "falhou",
                "fim": dt.datetime.now(dt.timezone.utc).isoformat(),
                "codigo": codigo,
                "tentativas": int(anterior.get("tentativas", 1)),
            }
            _salvar_estado(canal, estado)
        return codigo


def _slot_pendente(canal: Canal, config: Config, agora_utc: dt.datetime) -> str | None:
    local = agora_utc.astimezone(ZoneInfo(canal.fuso))
    estado = _estado(canal).get("slots", {})
    candidatos: list[tuple[dt.datetime, str]] = []
    for horario in canal.horarios:
        hora, minuto = map(int, horario.split(":"))
        alvo = local.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        atraso = (local - alvo).total_seconds() / 60
        slot = f"{alvo.date()}@{horario}@{canal.fuso}"
        registro = estado.get(slot) or {}
        status = registro.get("status")
        if status == "falhou":
            if int(registro.get("tentativas", 1)) >= 2:
                continue
            try:
                fim = dt.datetime.fromisoformat(registro.get("fim", ""))
                if (agora_utc - fim).total_seconds() < 15 * 60:
                    continue
            except (TypeError, ValueError):
                pass
        if 0 <= atraso <= config.tolerancia_minutos and status not in {"ok", "executando"}:
            candidatos.append((alvo, slot))
    return max(candidatos, default=(None, None))[1]


def canais_devidos(config: Config, forcar: str = "") -> list[tuple[Canal, str]]:
    if forcar:
        escolhidos = [c for c in config.canais if c.ativo]
        if forcar != "todos":
            escolhidos = [obter_canal(config, forcar)]
        return [(c, "manual") for c in escolhidos]

    agora = dt.datetime.now(dt.timezone.utc)
    devidos = []
    for canal in config.canais:
        if not canal.ativo:
            continue
        slot = _slot_pendente(canal, config, agora)
        if slot:
            devidos.append((canal, slot))
    return devidos


def validar(config: Config, conferir_arquivos: bool = True) -> int:
    avisos = []
    if conferir_arquivos:
        precisa_renderizador = any(c.modo == "gerar" for c in config.canais)
        if precisa_renderizador and not (BASE / "MoneyPrinterTurbo" / "cli.py").is_file():
            avisos.append("MoneyPrinterTurbo ainda nao foi baixado (normal antes da instalacao).")
        if not (BASE / "temas.txt").is_file():
            raise ErroConfig("temas.txt nao foi encontrado.")
    for canal in config.canais:
        if canal.ativo and not canal.horarios:
            avisos.append(f"{canal.id}: ativo, mas sem horarios; so roda manualmente.")
        if canal.ativo and "youtube" in canal.plataformas:
            token = BASE / "secrets" / f"youtube-{canal.id}.json"
            token_estado = DADOS / canal.id / "youtube_token.json"
            if not token.is_file() and not token_estado.is_file() and not (
                os.environ.get(f"YOUTUBE_TOKEN_{_sufixo(canal.id)}")
                or os.environ.get("YOUTUBE_TOKEN")
            ):
                avisos.append(f"{canal.id}: token do YouTube ainda nao configurado.")
        if canal.ativo and canal.modo == "drive":
            credencial_drive = (
                os.environ.get("DRIVE_CREDENTIALS")
                or (BASE / "secrets" / "drive_credentials.json").is_file()
                or (DADOS / "drive_credentials.json").is_file()
            )
            if not credencial_drive:
                avisos.append(
                    f"{canal.id}: sem credencial privada do Drive; "
                    "a pasta precisa estar publica."
                )
    print(f"Configuracao valida: {len(config.canais)} canal(is).")
    for aviso in avisos:
        print(f"AVISO: {aviso}")
    return 0


def listar(config: Config) -> None:
    for canal in config.canais:
        estado = "ATIVO" if canal.ativo else "desligado"
        print(f"{canal.id:25} {estado:9} {canal.modo:6} "
              f"{','.join(canal.plataformas):25} "
              f"{','.join(canal.horarios) or 'manual'}")


def daemon(config: Config, uma_vez: bool = False, teste: bool = False) -> int:
    os.environ["VIDEOBOT_PERMITE_CREDENCIAL_GERAL"] = (
        "1" if len([c for c in config.canais if c.ativo]) == 1 else "0"
    )
    print(
        f"Daemon ativo. Fuso padrao={config.fuso}; verificacao a cada "
        f"{config.intervalo_daemon_segundos}s. Ctrl+C encerra.",
        flush=True,
    )
    while True:
        devidos = canais_devidos(config)
        for canal, slot in devidos:
            executar(canal, teste=teste, slot=slot)
        if uma_vez:
            return 0
        try:
            time.sleep(config.intervalo_daemon_segundos)
        except KeyboardInterrupt:
            print("Daemon encerrado.")
            return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Central do videobot multicanal")
    p.add_argument("--config", type=Path, default=CONFIG_PADRAO)
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("validar", help="confere a configuracao")
    sub.add_parser("listar", help="lista canais e horarios")

    rodar = sub.add_parser("rodar", help="roda um canal agora")
    rodar.add_argument("--canal", required=True)
    rodar.add_argument("--teste", action="store_true")
    rodar.add_argument("--tema", default="", help="tema manual para gerar um Short")
    rodar.add_argument("--termos", default="", help="termos de video para o tema manual")
    rodar.add_argument("--slot", default="manual", help=argparse.SUPPRESS)

    dev = sub.add_parser("devidos", help="lista a matriz para o GitHub Actions")
    dev.add_argument("--json", action="store_true")
    dev.add_argument("--forcar", default="")

    d = sub.add_parser("daemon", help="fica ligado e executa nos horarios")
    d.add_argument("--uma-vez", action="store_true")
    d.add_argument("--teste", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = carregar_config(args.config)
        if args.comando == "validar":
            return validar(config)
        if args.comando == "listar":
            listar(config)
            return 0
        if args.comando == "rodar":
            tema = args.tema.strip()
            termos = args.termos.strip()
            if args.tema and not tema:
                raise ErroConfig("--tema nao pode ficar vazio.")
            if termos and not tema:
                raise ErroConfig("--termos exige --tema.")
            escolhido = obter_canal(config, args.canal)
            candidatos = [c for c in config.canais if c.ativo]
            if escolhido not in candidatos:
                candidatos.append(escolhido)
            os.environ.setdefault(
                "VIDEOBOT_PERMITE_CREDENCIAL_GERAL",
                "1" if len(candidatos) == 1 else "0",
            )
            return executar(
                escolhido, teste=args.teste, slot=args.slot,
                tema=tema, termos=termos,
            )
        if args.comando == "devidos":
            itens = canais_devidos(config, args.forcar)
            credenciais_necessarias = {c.id for c in config.canais if c.ativo}
            credenciais_necessarias.update(canal.id for canal, _ in itens)
            permite_geral = "1" if len(credenciais_necessarias) == 1 else "0"
            matriz = {
                "include": [
                    {
                        "canal": canal.id,
                        "slot": slot,
                        "segredo": _sufixo(canal.id),
                        "permite_geral": permite_geral,
                        "modo": canal.modo,
                    }
                    for canal, slot in itens
                ]
            }
            if args.json:
                print(json.dumps(matriz, separators=(",", ":")))
            else:
                for canal, slot in itens:
                    print(canal.id, slot)
            return 0
        if args.comando == "daemon":
            return daemon(config, uma_vez=args.uma_vez, teste=args.teste)
    except ErroConfig as exc:
        print(f"ERRO DE CONFIGURACAO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
