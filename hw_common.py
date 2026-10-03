from __future__ import annotations

import json
import subprocess
import sys
import uuid
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


def _wmi_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def parse_wmi_json(raw: str, properties: list[str]) -> list[dict[str, str]]:
    """Turn ConvertTo-Json output into rows limited to the requested properties.

    Numeric zeroes must be kept. ``str(value or "")`` treats ``0`` as missing,
    which drops speeds, sizes, and capacities when WMI returns more than one row.
    """
    if not raw or raw.startswith("<"):
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            rows: list[Any] = [data]
        elif isinstance(data, list):
            rows = [row for row in data if isinstance(row, dict)]
        else:
            return []
        return [{key: _wmi_cell(row.get(key)) for key in properties} for row in rows]
    except Exception:
        return []


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
    return parse_wmi_json(run_powershell(script), properties)


def format_mac_from_node() -> str:
    node = uuid.getnode()
    # uuid.getnode() sets the multicast bit when it has to invent an address.
    if node & (1 << 40):
        return "<unavailable: no hardware MAC found>"
    return ":".join(f"{(node >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))


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
