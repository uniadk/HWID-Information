from __future__ import annotations

import sys
import uuid

from hw_common import decode_wmi_bytes, pause, print_kv, section, wmi_query


def format_mac_from_node() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> shift) & 0xFF:02X}" for shift in range(40, -1, -8))


def show_cpu() -> None:
    rows = wmi_query("Win32_Processor", ["Name", "ProcessorId", "DeviceID"])
    cpu = rows[0] if rows else {}
    section("CPU")
    print_kv("Name", cpu.get("Name"))
    print_kv("Processor ID", cpu.get("ProcessorId"))
    print_kv("Device ID", cpu.get("DeviceID"))


def show_gpu() -> None:
    rows = wmi_query(
        "Win32_VideoController",
        ["Name", "PNPDeviceID", "DeviceID", "AdapterCompatibility"],
    )
    section("GPU")
    if not rows:
        print_kv("GPU", "<none detected>")
        return
    for i, gpu in enumerate(rows, 1):
        if len(rows) > 1:
            print(f"  --- GPU {i} ---")
        print_kv("Name", gpu.get("Name"))
        print_kv("PNP Device ID", gpu.get("PNPDeviceID"))
        print_kv("Device ID", gpu.get("DeviceID"))
        print_kv("Vendor ID", gpu.get("AdapterCompatibility"))


def show_ram() -> None:
    rows = wmi_query(
        "Win32_PhysicalMemory",
        ["BankLabel", "DeviceLocator", "PartNumber", "SerialNumber", "Capacity", "Speed"],
    )
    section("RAM")
    if not rows:
        print_kv("RAM", "<none detected>")
        return
    total = 0
    for i, mod in enumerate(rows, 1):
        try:
            total += int(mod.get("Capacity", "0") or 0)
        except ValueError:
            pass
        print(f"  --- Module {i} ---")
        print_kv("Slot", mod.get("DeviceLocator") or mod.get("BankLabel"))
        print_kv("Part number", mod.get("PartNumber"))
        print_kv("Serial", mod.get("SerialNumber"))
        try:
            gb = int(mod.get("Capacity", "0") or 0) / (1024 ** 3)
            print_kv("Capacity", f"{gb:.2f} GB")
        except ValueError:
            print_kv("Capacity", mod.get("Capacity"))
        print_kv("Speed", f"{mod.get('Speed', '?')} MHz")
    if total:
        print_kv("Total", f"{total / (1024 ** 3):.2f} GB")


def show_monitors() -> None:
    wmi_monitors = wmi_query(
        "WmiMonitorID",
        ["InstanceName", "ManufacturerName", "ProductCodeID", "SerialNumberID", "UserFriendlyName"],
        namespace="root/wmi",
    )
    desktop_monitors = wmi_query(
        "Win32_DesktopMonitor",
        ["Name", "PNPDeviceID", "DeviceID"],
    )

    section("MONITOR")
    if wmi_monitors:
        for i, mon in enumerate(wmi_monitors, 1):
            print(f"  --- Monitor {i} ---")
            print_kv("Instance", mon.get("InstanceName"))
            print_kv("Manufacturer", decode_wmi_bytes(mon.get("ManufacturerName", "")))
            print_kv("Product code", decode_wmi_bytes(mon.get("ProductCodeID", "")))
            print_kv("Serial", decode_wmi_bytes(mon.get("SerialNumberID", "")))
            print_kv("Friendly name", decode_wmi_bytes(mon.get("UserFriendlyName", "")))
    elif desktop_monitors:
        for i, mon in enumerate(desktop_monitors, 1):
            print(f"  --- Monitor {i} ---")
            print_kv("Name", mon.get("Name"))
            print_kv("PNP Device ID", mon.get("PNPDeviceID"))
            print_kv("Device ID", mon.get("DeviceID"))
    else:
        print_kv("Monitor", "<none detected>")


def show_other_ids() -> None:
    board = wmi_query("Win32_BaseBoard", ["Manufacturer", "Product", "SerialNumber"])
    bios = wmi_query("Win32_BIOS", ["SerialNumber"])
    system = wmi_query("Win32_ComputerSystemProduct", ["UUID"])
    disks = wmi_query("Win32_DiskDrive", ["Model", "SerialNumber"])
    net = wmi_query(
        "Win32_NetworkAdapter",
        ["NetConnectionID", "Name", "MACAddress"],
    )

    section("OTHER IDs")
    if board:
        print_kv("Motherboard", board[0].get("Product"))
        print_kv("Board serial", board[0].get("SerialNumber"))
    if bios:
        print_kv("BIOS serial", bios[0].get("SerialNumber"))
    if system:
        print_kv("System UUID", system[0].get("UUID"))

    for i, disk in enumerate(disks, 1):
        print_kv(f"Disk {i} serial", f"{disk.get('Model', '?')} | {disk.get('SerialNumber', '?')}")

    print_kv("MAC address", format_mac_from_node())
    for row in net:
        mac = (row.get("MACAddress") or "").strip()
        if not mac:
            continue
        label = row.get("NetConnectionID") or row.get("Name") or "Adapter"
        print_kv(label, mac)


def main() -> None:
    if sys.platform != "win32":
        print("This script is optimized for Windows. Some data may be missing on other OSes.")
        print()

    print()
    print("  HARDWARE ID — LITE")
    print("  " + "-" * 28)

    show_cpu()
    show_gpu()
    show_ram()
    show_monitors()
    show_other_ids()

    section("DONE")
    pause()


if __name__ == "__main__":
    main()
