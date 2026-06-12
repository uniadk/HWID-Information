from __future__ import annotations

import hashlib
import platform
import sys
import uuid
import winreg
from typing import Any

from hw_common import pause, print_kv, section, wmi_query


def format_mac_from_node() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))


def get_registry_machine_guid() -> str:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        )
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(value)
    except OSError as exc:
        return f"<unavailable: {exc}>"


def get_volume_serial(drive: str = "C:") -> str:
    from hw_common import run_powershell

    script = (
        f"(Get-CimInstance -ClassName Win32_LogicalDisk "
        f"-Filter \"DeviceID='{drive}'\").VolumeSerialNumber"
    )
    return run_powershell(script) or "<unavailable>"


def hash_id(*parts: str, algo: str = "sha256") -> str:
    joined = "|".join(p.strip() for p in parts if p and p.strip())
    if not joined:
        return "<empty source>"
    digest = hashlib.new(algo, joined.encode("utf-8", errors="replace")).hexdigest()
    return digest.upper()


def collect_hardware() -> dict[str, Any]:
    cpu_rows = wmi_query(
        "Win32_Processor",
        ["Name", "Manufacturer", "ProcessorId", "NumberOfCores", "NumberOfLogicalProcessors"],
    )
    board_rows = wmi_query("Win32_BaseBoard", ["Manufacturer", "Product", "SerialNumber"])
    bios_rows = wmi_query("Win32_BIOS", ["Manufacturer", "SerialNumber", "SMBIOSBIOSVersion"])
    system_rows = wmi_query(
        "Win32_ComputerSystemProduct",
        ["UUID", "Name", "IdentifyingNumber", "Vendor"],
    )
    disk_rows = wmi_query("Win32_DiskDrive", ["Model", "SerialNumber", "Size", "InterfaceType"])
    gpu_rows = wmi_query("Win32_VideoController", ["Name", "DriverVersion", "AdapterRAM"])
    mem_rows = wmi_query("Win32_PhysicalMemory", ["Manufacturer", "Capacity", "Speed", "PartNumber"])
    net_rows = wmi_query(
        "Win32_NetworkAdapter",
        ["Name", "MACAddress", "PNPDeviceID", "NetConnectionID"],
    )
    os_rows = wmi_query(
        "Win32_OperatingSystem",
        ["Caption", "Version", "BuildNumber", "SerialNumber", "InstallDate"],
    )

    total_ram = 0
    for row in mem_rows:
        try:
            total_ram += int(row.get("Capacity", "0") or 0)
        except ValueError:
            pass

    return {
        "cpu": cpu_rows[0] if cpu_rows else {},
        "board": board_rows[0] if board_rows else {},
        "bios": bios_rows[0] if bios_rows else {},
        "system": system_rows[0] if system_rows else {},
        "disks": disk_rows,
        "gpus": gpu_rows,
        "memory_modules": mem_rows,
        "total_ram_bytes": total_ram,
        "network_adapters": [r for r in net_rows if (r.get("MACAddress") or "").strip()],
        "os": os_rows[0] if os_rows else {},
        "machine_guid": get_registry_machine_guid(),
        "volume_serial_c": get_volume_serial("C:"),
        "mac_python": format_mac_from_node(),
    }


def show_hardware(hw: dict[str, Any]) -> None:
    section("SYSTEM OVERVIEW")
    print_kv("Computer name", platform.node())
    print_kv("OS", platform.platform())
    print_kv("Architecture", platform.machine())
    print_kv("Python", sys.version.split()[0])

    os_info = hw["os"]
    if os_info:
        print_kv("Windows caption", os_info.get("Caption"))
        print_kv("Windows version", os_info.get("Version"))
        print_kv("Windows build", os_info.get("BuildNumber"))
        print_kv("Windows serial", os_info.get("SerialNumber"))

    section("PROCESSOR")
    cpu = hw["cpu"]
    print_kv("Name", cpu.get("Name"))
    print_kv("Manufacturer", cpu.get("Manufacturer"))
    print_kv("Processor ID", cpu.get("ProcessorId"))
    print_kv("Cores / Threads", f"{cpu.get('NumberOfCores', '?')} / {cpu.get('NumberOfLogicalProcessors', '?')}")

    section("MOTHERBOARD & BIOS")
    board = hw["board"]
    print_kv("Board manufacturer", board.get("Manufacturer"))
    print_kv("Board product", board.get("Product"))
    print_kv("Board serial", board.get("SerialNumber"))
    bios = hw["bios"]
    print_kv("BIOS manufacturer", bios.get("Manufacturer"))
    print_kv("BIOS serial", bios.get("SerialNumber"))
    print_kv("BIOS version", bios.get("SMBIOSBIOSVersion"))

    section("SYSTEM PRODUCT (SMBIOS)")
    system = hw["system"]
    print_kv("System UUID", system.get("UUID"))
    print_kv("Product name", system.get("Name"))
    print_kv("Product ID", system.get("IdentifyingNumber"))
    print_kv("Vendor", system.get("Vendor"))

    section("MEMORY")
    if hw["total_ram_bytes"]:
        gb = hw["total_ram_bytes"] / (1024 ** 3)
        print_kv("Total RAM", f"{gb:.2f} GB ({hw['total_ram_bytes']} bytes)")
    for i, mod in enumerate(hw["memory_modules"], 1):
        cap = mod.get("Capacity", "0")
        try:
            cap_gb = int(cap) / (1024 ** 3)
            cap_text = f"{cap_gb:.2f} GB"
        except ValueError:
            cap_text = cap
        print_kv(f"Module {i}", f"{mod.get('Manufacturer', '?')} {cap_text} @ {mod.get('Speed', '?')} MHz")

    section("STORAGE")
    for i, disk in enumerate(hw["disks"], 1):
        size = disk.get("Size", "0")
        try:
            size_gb = int(size) / (1024 ** 3)
            size_text = f"{size_gb:.2f} GB"
        except ValueError:
            size_text = size
        print_kv(
            f"Disk {i}",
            f"{disk.get('Model', '?')} | Serial: {disk.get('SerialNumber', '?')} | {size_text}",
        )
    print_kv("C: volume serial", hw["volume_serial_c"])

    section("GRAPHICS")
    for i, gpu in enumerate(hw["gpus"], 1):
        ram = gpu.get("AdapterRAM", "")
        try:
            ram_gb = int(ram) / (1024 ** 3)
            ram_text = f"{ram_gb:.2f} GB"
        except (ValueError, TypeError):
            ram_text = ram or "?"
        print_kv(f"GPU {i}", f"{gpu.get('Name', '?')} | Driver {gpu.get('DriverVersion', '?')} | VRAM {ram_text}")

    section("NETWORK")
    print_kv("MAC (uuid.getnode)", hw["mac_python"])
    for i, adapter in enumerate(hw["network_adapters"], 1):
        print_kv(
            f"Adapter {i}",
            f"{adapter.get('NetConnectionID') or adapter.get('Name', '?')} | MAC {adapter.get('MACAddress', '?')}",
        )

    section("WINDOWS IDENTIFIERS")
    print_kv("Registry MachineGuid", hw["machine_guid"])


def show_hwids(hw: dict[str, Any]) -> None:
    cpu_id = hw["cpu"].get("ProcessorId", "")
    board_serial = hw["board"].get("SerialNumber", "")
    bios_serial = hw["bios"].get("SerialNumber", "")
    smbios_uuid = hw["system"].get("UUID", "")
    machine_guid = hw["machine_guid"]
    volume_serial = hw["volume_serial_c"]
    mac = hw["mac_python"]

    disk_serials = [d.get("SerialNumber", "").strip() for d in hw["disks"] if d.get("SerialNumber")]
    primary_disk_serial = disk_serials[0] if disk_serials else ""

    section("5 COMMON APP HWID METHODS")
    print()
    print("  Apps often mix these values and hash them. Below are raw IDs and")
    print("  typical compiled fingerprints (SHA-256 unless noted).")
    print()

    hwid1 = machine_guid if not machine_guid.startswith("<") else hash_id("machine-guid-fallback", smbios_uuid)
    print("  [1] Windows MachineGuid (registry)")
    print_kv("Source", r"HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid", indent=4)
    print_kv("Raw ID", hwid1, indent=4)
    print_kv("SHA-256", hash_id(hwid1), indent=4)
    print()

    hwid2_raw = smbios_uuid
    hwid2 = hash_id(hwid2_raw) if hwid2_raw else "<empty>"
    print("  [2] SMBIOS System UUID")
    print_kv("Source", "Win32_ComputerSystemProduct.UUID", indent=4)
    print_kv("Raw ID", hwid2_raw or "<unknown>", indent=4)
    print_kv("SHA-256", hwid2, indent=4)
    print()

    composite = f"{cpu_id}|{board_serial}|{bios_serial}"
    hwid3 = hash_id(cpu_id, board_serial, bios_serial)
    print("  [3] CPU ID + Motherboard + BIOS serial (composite hash)")
    print_kv("Source", "ProcessorId + BaseBoard.SerialNumber + BIOS.SerialNumber", indent=4)
    print_kv("Combined", composite, indent=4)
    print_kv("SHA-256", hwid3, indent=4)
    print()

    hwid4_raw = primary_disk_serial
    hwid4 = hash_id(hwid4_raw) if hwid4_raw else "<empty>"
    print("  [4] Primary physical disk serial")
    print_kv("Source", "Win32_DiskDrive.SerialNumber (first drive)", indent=4)
    print_kv("Raw ID", hwid4_raw or "<unknown>", indent=4)
    print_kv("SHA-256", hwid4, indent=4)
    print()

    mac_clean = mac.replace(":", "").upper()
    vol_clean = str(volume_serial).strip().upper()
    hwid5_raw = f"{mac_clean}-{vol_clean}"
    hwid5 = hash_id(mac_clean, vol_clean)
    print("  [5] MAC address + C: volume serial (composite hash)")
    print_kv("Source", "uuid.getnode() MAC + Win32_LogicalDisk.VolumeSerialNumber", indent=4)
    print_kv("Combined", hwid5_raw, indent=4)
    print_kv("SHA-256", hwid5, indent=4)
    print_kv("MD5 (legacy apps)", hash_id(mac_clean, vol_clean, algo="md5"), indent=4)


def main() -> None:
    if sys.platform != "win32":
        print("This script is optimized for Windows. Some data may be missing on other OSes.")
        print()

    print()
    print("  HARDWARE INFORMATION & HWID FINGERPRINTS")
    print("  " + "-" * 44)

    hw = collect_hardware()
    show_hardware(hw)
    show_hwids(hw)

    section("DONE")
    pause()


if __name__ == "__main__":
    main()
