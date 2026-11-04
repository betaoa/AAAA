"""Valida arquivos .jsonl de treino e (opcionalmente) checa sintaxe Luau.

Uso:
    python scripts/validate_dataset.py dataset/*.jsonl
Se `luau-analyze` estiver no PATH, cada bloco de codigo e analisado.
"""
import collections
import json
import re
import shutil
import subprocess
import sys
import tempfile

ROLES = {"system", "user", "assistant"}
FENCE = re.compile(r"```lua\n(.*?)\n```", re.DOTALL)


def check_row(row: dict) -> list[str]:
    errs = []
    msgs = row.get("messages")
    if not isinstance(msgs, list) or len(msgs) < 2:
        return ["campo 'messages' ausente ou curto demais"]
    for m in msgs:
        if m.get("role") not in ROLES or not str(m.get("content", "")).strip():
            errs.append(f"mensagem invalida: {str(m)[:60]}")
    if msgs[-1].get("role") != "assistant":
        errs.append("ultima mensagem precisa ser 'assistant'")
    elif not FENCE.search(msgs[-1].get("content", "")):
        errs.append("resposta sem bloco ```lua")
    return errs


def luau_errors(code: str) -> str:
    exe = shutil.which("luau-analyze")
    if not exe:
        return ""
    with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False) as t:
        t.write(code)
    r = subprocess.run([exe, t.name], capture_output=True, text=True)
    return r.stdout + r.stderr if r.returncode else ""


def main(paths: list[str]) -> int:
    total = bad = 0
    tags = collections.Counter()
    seen = set()
    for path in paths:
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"{path}:{n}: JSON invalido ({e})")
                bad += 1
                continue
            errs = check_row(row)
            key = json.dumps(row.get("messages", [])[-2:], sort_keys=True)
            if key in seen:
                errs.append("duplicado")
            seen.add(key)
            if not errs:
                m = FENCE.search(row["messages"][-1]["content"])
                lerr = luau_errors(m.group(1))
                if lerr:
                    errs.append("luau-analyze: " + lerr.strip()[:200])
            tags.update(row.get("tags", []))
            if errs:
                bad += 1
                print(f"{path}:{n}: " + "; ".join(errs))
    print(f"total={total} invalidos={bad} tags={dict(tags)}")
    if not shutil.which("luau-analyze"):
        print("aviso: luau-analyze nao encontrado; sintaxe Luau NAO foi verificada")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else 2)
