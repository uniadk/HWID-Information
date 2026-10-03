# HWID-Information

A small Python utility for displaying hardware/HWID information.  
Includes both a full information script and a lightweight version.

## Files

| File | Description |
|---|---|
| `hardware_info.py` | Displays full hardware and system information. |
| `hardware_info_lite.py` | Displays less information, mainly intended for spoofer validation. |
| `hw_common.py` | Shared helper code used by the scripts. Dependency file does not need to be run directly. |

## Usage

Download all 3 files and place them inside a folder and run your desired version.

Clone the repository:

```bash
git clone https://github.com/uniadk/HWID-Information.git
cd HWID-Information
python hardware_info.py
python hardware_info_lite.py
```

These scripts are written for Windows. On other systems they still start, but WMI and registry data will be missing.
