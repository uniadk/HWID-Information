from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def section(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def run_powershell(script: str) -> str:
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=flags,
        )
        out = (result.stdout or "").strip()
        if out:
            return out
        return (result.stderr or "").strip()
    except Exception as exc:
        return f"<unavailable: {exc}>"


def wmi_query(
    class_name: str,
    properties: list[str],
    namespace: str = "root/cimv2",
) -> list[dict[str, str]]:
    props = ",".join(properties)
    script = (
        f"Get-CimInstance -Namespace '{namespace}' -ClassName {class_name} | "
        f"Select-Object -Property {props} | "
        "ConvertTo-Json -Compress"
    )
    raw = run_powershell(script)
    if not raw or raw.startswith("<"):
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return [{k: str(v if v is not None else "") for k, v in data.items()}]
        if isinstance(data, list):
            return [{k: str(row.get(k, "") or "") for k in properties} for row in data]
    except Exception:
        pass
    return []


def decode_wmi_bytes(value: str) -> str:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        bracketed = value
    elif value.startswith("{") and value.endswith("}"):
        bracketed = f"[{value[1:-1]}]"
    else:
        return value
    try:
        parts = [int(p.strip()) for p in bracketed[1:-1].split(",") if p.strip()]
        return "".join(chr(p) for p in parts if p > 0).strip()
    except ValueError:
        return value


def print_kv(label: str, value: Any, indent: int = 2) -> None:
    pad = " " * indent
    text = str(value).strip() if value is not None else ""
    if not text:
        text = "<unknown>"
    print(f"{pad}{label:<22} {text}")


def pause() -> None:
    print()
    print("  Press Enter to close this window...")
    try:
        input()
    except EOFError:
        pass
