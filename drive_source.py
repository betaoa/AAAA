#!/usr/bin/env python3
"""Seleciona e baixa um video de uma pasta do Google Drive.

Pastas publicas funcionam apenas com o link. Para uma pasta privada, defina
DRIVE_CREDENTIALS_FILE com JSON de conta de servico ou token OAuth autorizado.
"""

from __future__ import annotations

import io
import json
import random
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

EXTENSOES = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
PASTA_MIME = "application/vnd.google-apps.folder"
ATALHO_MIME = "application/vnd.google-apps.shortcut"


class ErroDrive(RuntimeError):
    pass


@dataclass(frozen=True)
class ArquivoDrive:
    id: str
    nome: str
    caminho: str = ""


def extrair_id(url_ou_id: str) -> str:
    texto = url_ou_id.strip()
    achado = re.search(r"/folders/([A-Za-z0-9_-]+)", texto)
    if achado:
        return achado.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", texto):
        return texto
    raise ErroDrive(f"Link de pasta invalido: {texto}")


def _eh_video(nome: str, mime: str = "") -> bool:
    return Path(nome).suffix.lower() in EXTENSOES or mime.startswith("video/")


def _credenciais(caminho: str):
    arquivo = Path(caminho)
    if not caminho or not arquivo.is_file():
        return None
    try:
        info = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErroDrive(f"Credencial do Drive invalida: {exc}") from None

    escopos = ["https://www.googleapis.com/auth/drive.readonly"]
    if info.get("type") == "service_account":
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_info(
            info, scopes=escopos
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        cred = Credentials.from_authorized_user_info(info, scopes=escopos)
        if cred.expired and cred.refresh_token:
            cred.refresh(Request())
        return cred
    except (KeyError, ValueError) as exc:
        raise ErroDrive(
            "O JSON do Drive precisa ser conta de servico ou token OAuth."
        ) from exc


def _servico(caminho_credencial: str):
    cred = _credenciais(caminho_credencial)
    if cred is None:
        return None
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=cred, cache_discovery=False)


def _listar_api(servico, pasta_id: str) -> list[ArquivoDrive]:
    encontrados: list[ArquivoDrive] = []
    pendentes = [(pasta_id, "")]
    visitadas: set[str] = set()
    while pendentes:
        atual, prefixo = pendentes.pop()
        if atual in visitadas:
            continue
        visitadas.add(atual)
        token = None
        while True:
            resposta = servico.files().list(
                q=f"'{atual}' in parents and trashed = false",
                fields=(
                    "nextPageToken,files(id,name,mimeType,size,"
                    "shortcutDetails(targetId,targetMimeType))"
                ),
                pageSize=1000,
                pageToken=token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for item in resposta.get("files", []):
                alvo_id = item["id"]
                alvo_mime = item.get("mimeType", "")
                if alvo_mime == ATALHO_MIME:
                    detalhes = item.get("shortcutDetails") or {}
                    alvo_id = detalhes.get("targetId") or alvo_id
                    alvo_mime = detalhes.get("targetMimeType") or alvo_mime
                nome = item.get("name") or alvo_id
                caminho = f"{prefixo}/{nome}".lstrip("/")
                if alvo_mime == PASTA_MIME:
                    pendentes.append((alvo_id, caminho))
                elif _eh_video(nome, alvo_mime):
                    encontrados.append(ArquivoDrive(alvo_id, nome, caminho))
            token = resposta.get("nextPageToken")
            if not token:
                break
    return encontrados


def _listar_publico(url: str) -> list[ArquivoDrive]:
    try:
        import gdown

        itens = gdown.download_folder(
            url=url, skip_download=True, quiet=True, use_cookies=False
        )
    except Exception as exc:
        raise ErroDrive(
            "A pasta nao esta publica. Configure DRIVE_CREDENTIALS ou "
            "compartilhe a central com a conta de servico."
        ) from exc
    return [
        ArquivoDrive(x.id, Path(x.path).name, x.path)
        for x in (itens or [])
        if _eh_video(x.path)
    ]


def listar_videos(url: str, credencial: str = "") -> tuple[list[ArquivoDrive], object]:
    servico = _servico(credencial)
    if servico is not None:
        try:
            return _listar_api(servico, extrair_id(url)), servico
        except Exception as exc:  # noqa: BLE001 - SDK externo
            raise ErroDrive(f"Nao consegui listar a pasta privada: {exc}") from None
    return _listar_publico(url), None


def _listar_local(raiz: str, nome_pasta: str) -> list[ArquivoDrive]:
    pasta = Path(raiz).expanduser() / nome_pasta
    if not pasta.is_dir():
        return []
    encontrados = []
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES:
            continue
        relativo = caminho.relative_to(pasta).as_posix()
        arquivo_id = "local-" + sha256(relativo.encode("utf-8")).hexdigest()[:32]
        encontrados.append(ArquivoDrive(arquivo_id, caminho.name, str(caminho)))
    return encontrados


def _nome_seguro(nome: str) -> str:
    base = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", nome).strip(" .")
    return base[:180] or "video.mp4"


def baixar(arquivo: ArquivoDrive, destino: Path, servico=None) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    saida = destino / _nome_seguro(arquivo.nome)
    if saida.suffix.lower() not in EXTENSOES:
        saida = saida.with_suffix(".mp4")
    if servico is None:
        import gdown

        resultado = gdown.download(
            id=arquivo.id, output=str(saida), quiet=True, use_cookies=False
        )
        if not resultado:
            raise ErroDrive(f"Falhou ao baixar {arquivo.nome}")
        return Path(resultado)

    from googleapiclient.http import MediaIoBaseDownload

    requisicao = servico.files().get_media(
        fileId=arquivo.id, supportsAllDrives=True
    )
    memoria = io.FileIO(saida, "wb")
    downloader = MediaIoBaseDownload(memoria, requisicao, chunksize=8 * 1024 * 1024)
    concluido = False
    try:
        while not concluido:
            _, concluido = downloader.next_chunk()
    finally:
        memoria.close()
    return saida


def escolher_e_baixar(
    url: str,
    pasta_destino: Path,
    usados_path: Path,
    credencial: str = "",
    sync_root: str = "",
    folder_name: str = "",
) -> tuple[ArquivoDrive, Path]:
    videos = _listar_local(sync_root, folder_name) if sync_root and folder_name else []
    servico = None
    origem_local = bool(videos)
    if not videos:
        videos, servico = listar_videos(url, credencial)
    if not videos:
        raise ErroDrive("A pasta nao contem nenhum video compativel.")
    usados = set()
    if usados_path.is_file():
        usados = {
            linha.strip()
            for linha in usados_path.read_text(encoding="utf-8").splitlines()
            if linha.strip()
        }
    disponiveis = [video for video in videos if video.id not in usados]
    if not disponiveis:
        disponiveis = videos
    escolhido = random.choice(disponiveis)
    if origem_local:
        return escolhido, Path(escolhido.caminho)
    return escolhido, baixar(escolhido, pasta_destino, servico)


def marcar_usado(caminho: Path, arquivo_id: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as f:
        f.write(arquivo_id + "\n")
