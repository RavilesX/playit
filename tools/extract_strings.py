"""Sincroniza locales/*.json con el código: agrega las claves nuevas de
tr()/N_() con valor vacío (cae al español) y lista las huérfanas.

Uso: python tools/extract_strings.py [--check]
--check no escribe nada y sale con 1 si hay claves sin traducir u huérfanas."""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ("en", "pt")


def code_keys() -> set[str]:
    keys = set()
    for path in ROOT.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("tr", "N_") and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
    return keys


def main(check: bool) -> int:
    keys = code_keys()
    bad = 0
    for code in LOCALES:
        file = ROOT / "locales" / f"{code}.json"
        data = json.loads(file.read_text(encoding="utf-8"))
        missing = sorted(keys - data.keys())
        orphan = sorted(data.keys() - keys)
        empty = [k for k in keys if k in data and not data[k]]
        print(f"{code}: {len(missing)} nuevas, {len(orphan)} huérfanas, "
              f"{len(empty)} sin traducir")
        for k in orphan:
            print(f"  huérfana: {k!r}")
        bad += len(missing) + len(orphan) + len(empty)
        if not check:
            for k in missing:
                data[k] = ""
            file.write_text(
                json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
    return 1 if check and bad else 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
