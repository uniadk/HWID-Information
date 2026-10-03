import contextlib
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hardware_info
import hardware_info_lite
import hw_common
from hw_common import decode_wmi_bytes, format_mac_from_node, parse_wmi_json


def _sample_hw(**overrides):
    hw = {
        "cpu": {"ProcessorId": "CPU1"},
        "board": {"SerialNumber": "BOARD"},
        "bios": {"SerialNumber": "BIOS"},
        "system": {"UUID": "UUID-1"},
        "disks": [{"SerialNumber": "DISK1"}],
        "machine_guid": "GUID-1",
        "volume_serial_c": "aabbccdd",
        "mac_python": "aa:bb:cc:dd:ee:ff",
    }
    hw.update(overrides)
    return hw


def _show_hwids(hw):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        hardware_info.show_hwids(hw)
    return buffer.getvalue()


class WmiParseTests(unittest.TestCase):
    def test_multi_row_keeps_numeric_zero(self):
        raw = json.dumps(
            [
                {"Speed": 0, "Capacity": 0},
                {"Speed": 3200, "Capacity": 17179869184},
            ]
        )
        rows = parse_wmi_json(raw, ["Speed", "Capacity"])
        self.assertEqual(rows[0], {"Speed": "0", "Capacity": "0"})
        self.assertEqual(rows[1]["Speed"], "3200")
        self.assertEqual(rows[1]["Capacity"], "17179869184")

    def test_single_object_keeps_zero_and_requested_keys_only(self):
        raw = json.dumps({"Speed": 0, "Extra": "ignored"})
        self.assertEqual(parse_wmi_json(raw, ["Speed"]), [{"Speed": "0"}])

    def test_null_missing_and_invalid_payloads(self):
        self.assertEqual(parse_wmi_json("", ["Speed"]), [])
        self.assertEqual(parse_wmi_json("<unavailable: boom>", ["Speed"]), [])
        self.assertEqual(parse_wmi_json("not-json", ["Speed"]), [])
        self.assertEqual(parse_wmi_json("[]", ["Speed"]), [])
        self.assertEqual(parse_wmi_json("null", ["Speed"]), [])
        self.assertEqual(
            parse_wmi_json(json.dumps([{"Speed": None}]), ["Speed"]),
            [{"Speed": ""}],
        )

    def test_non_dict_rows_are_skipped(self):
        raw = json.dumps([{"Speed": 2400}, "bad", 3])
        self.assertEqual(parse_wmi_json(raw, ["Speed"]), [{"Speed": "2400"}])

    def test_monitor_byte_array_survives_stringifying(self):
        raw = json.dumps({"ManufacturerName": [65, 67, 69, 82, 0, 32]})
        rows = parse_wmi_json(raw, ["ManufacturerName"])
        self.assertEqual(decode_wmi_bytes(rows[0]["ManufacturerName"]), "ACER")

    def test_wmi_query_uses_parser(self):
        raw = json.dumps([{"Speed": 0}])
        with mock.patch("hw_common.run_powershell", return_value=raw) as run:
            rows = hw_common.wmi_query("Win32_PhysicalMemory", ["Speed"], "root/cimv2")
        self.assertEqual(rows, [{"Speed": "0"}])
        script = run.call_args.args[0]
        self.assertIn("Win32_PhysicalMemory", script)
        self.assertIn("root/cimv2", script)
        self.assertIn("ConvertTo-Json -Compress", script)


class MacAndFingerprintTests(unittest.TestCase):
    def test_hardware_mac_is_formatted(self):
        with mock.patch("hw_common.uuid.getnode", return_value=0xAABBCCDDEEFF):
            self.assertEqual(format_mac_from_node(), "AA:BB:CC:DD:EE:FF")

    def test_locally_administered_mac_is_kept(self):
        with mock.patch("hw_common.uuid.getnode", return_value=0x0242AC110002):
            self.assertEqual(format_mac_from_node(), "02:42:AC:11:00:02")

    def test_random_getnode_address_is_not_a_hardware_mac(self):
        with mock.patch("hw_common.uuid.getnode", return_value=(1 << 40) | 0x2A):
            self.assertEqual(
                format_mac_from_node(),
                "<unavailable: no hardware MAC found>",
            )

    def test_complete_hwid5_matches_previous_hash(self):
        output = _show_hwids(_sample_hw())
        self.assertIn("AABBCCDDEEFF-AABBCCDD", output)
        self.assertIn(hardware_info.hash_id("AABBCCDDEEFF", "AABBCCDD"), output)
        self.assertIn(
            hardware_info.hash_id("AABBCCDDEEFF", "AABBCCDD", algo="md5"),
            output,
        )
        self.assertIn(hardware_info.hash_id("CPU1", "BOARD", "BIOS"), output)
        self.assertIn(hardware_info.hash_id("GUID-1"), output)

    def test_missing_mac_is_not_hashed_into_hwid5(self):
        output = _show_hwids(
            _sample_hw(mac_python="<unavailable: no hardware MAC found>")
        )
        self.assertIn("<unknown>-AABBCCDD", output)
        bogus = hardware_info.hash_id(
            "<UNAVAILABLE: NO HARDWARE MAC FOUND>",
            "AABBCCDD",
        )
        self.assertNotIn(bogus, output)
        self.assertEqual(output.count("<unavailable>"), 2)

    def test_missing_volume_serial_is_not_hashed_into_hwid5(self):
        output = _show_hwids(_sample_hw(volume_serial_c="<unavailable: timeout>"))
        self.assertIn("AABBCCDDEEFF-<unknown>", output)
        bogus = hardware_info.hash_id("AABBCCDDEEFF", "<UNAVAILABLE: TIMEOUT>")
        self.assertNotIn(bogus, output)


class DisplayAndStartupTests(unittest.TestCase):
    def test_adapter_ram_unsigned_display(self):
        self.assertEqual(hardware_info.format_adapter_ram("1073741824"), "1.00 GB")
        self.assertEqual(hardware_info.format_adapter_ram("-1"), "4.00 GB")
        self.assertEqual(hardware_info.format_adapter_ram("-2147483648"), "2.00 GB")
        self.assertEqual(hardware_info.format_adapter_ram("0"), "0.00 GB")
        self.assertEqual(hardware_info.format_adapter_ram(""), "?")
        self.assertEqual(hardware_info.format_adapter_ram(None), "?")
        self.assertEqual(hardware_info.format_adapter_ram("n/a"), "n/a")

    def test_gpu_compatibility_is_labeled_manufacturer(self):
        rows = [
            {
                "Name": "Example GPU",
                "PNPDeviceID": r"PCI\VEN_10DE",
                "DeviceID": "VideoController1",
                "AdapterCompatibility": "NVIDIA",
            }
        ]
        with mock.patch("hardware_info_lite.wmi_query", return_value=rows):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                hardware_info_lite.show_gpu()
        output = buffer.getvalue()
        self.assertIn("Manufacturer", output)
        self.assertIn("NVIDIA", output)
        self.assertNotIn("Vendor ID", output)

    def test_registry_import_error_is_reported(self):
        previous = sys.modules.get("winreg")
        sys.modules["winreg"] = None
        try:
            result = hardware_info.get_registry_machine_guid()
        finally:
            if previous is None:
                sys.modules.pop("winreg", None)
            else:
                sys.modules["winreg"] = previous
        self.assertEqual(result, "<unavailable: winreg is only supported on Windows>")

    def test_registry_key_closes_when_query_fails(self):
        events = []

        class Key:
            def __enter__(self):
                events.append("enter")
                return self

            def __exit__(self, exc_type, exc, tb):
                events.append("exit")
                return False

        module = types.ModuleType("winreg")
        module.HKEY_LOCAL_MACHINE = object()
        module.OpenKey = lambda *args, **kwargs: events.append("open") or Key()

        def query(key, name):
            events.append(name)
            raise OSError("denied")

        module.QueryValueEx = query
        previous = sys.modules.get("winreg")
        sys.modules["winreg"] = module
        try:
            result = hardware_info.get_registry_machine_guid()
        finally:
            if previous is None:
                sys.modules.pop("winreg", None)
            else:
                sys.modules["winreg"] = previous
        self.assertEqual(events, ["open", "enter", "MachineGuid", "exit"])
        self.assertTrue(result.startswith("<unavailable: "))
        self.assertIn("denied", result)

    def test_registry_returns_machine_guid(self):
        events = []

        class Key:
            def __enter__(self):
                events.append("enter")
                return self

            def __exit__(self, exc_type, exc, tb):
                events.append("exit")
                return False

        module = types.ModuleType("winreg")
        module.HKEY_LOCAL_MACHINE = object()
        module.OpenKey = lambda *args, **kwargs: Key()
        module.QueryValueEx = lambda key, name: ("guid-123", 1)
        previous = sys.modules.get("winreg")
        sys.modules["winreg"] = module
        try:
            result = hardware_info.get_registry_machine_guid()
        finally:
            if previous is None:
                sys.modules.pop("winreg", None)
            else:
                sys.modules["winreg"] = previous
        self.assertEqual(result, "guid-123")
        self.assertEqual(events, ["enter", "exit"])

    def test_full_script_starts_without_crashing(self):
        with mock.patch("hw_common.run_powershell", return_value=""):
            with mock.patch("builtins.input", return_value=""):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    hardware_info.main()
        output = buffer.getvalue()
        self.assertIn("HARDWARE INFORMATION", output)
        if sys.platform != "win32":
            self.assertIn("optimized for Windows", output)
            self.assertIn("winreg is only supported on Windows", output)

    def test_lite_script_starts_without_crashing(self):
        with mock.patch("hw_common.run_powershell", return_value=""):
            with mock.patch("builtins.input", return_value=""):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    hardware_info_lite.main()
        self.assertIn("HARDWARE ID", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
