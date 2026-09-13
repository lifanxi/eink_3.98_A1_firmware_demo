#!/usr/bin/env python3
"""Verify the built image and package the A1 firmware and macOS sender."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import site
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--platformio-home', type=Path, default=Path.home() / '.platformio')
parser.add_argument('--output', type=Path, default=ROOT / 'dist/ble-a1')
args = parser.parse_args()
packages = args.platformio_home / 'packages'
site.addsitedir(str(packages / 'tool-esptoolpy/_contrib'))
sys.path.insert(0, str(packages / 'tool-esptoolpy'))
from esptool.bin_image import ESP32C3FirmwareImage
sys.path.insert(0, str(packages / 'framework-arduinoespressif32/tools'))
from gen_esp32part import PartitionTable

build = ROOT / '.pio/build/huawei_a1'
merged = (build / 'firmware_merged.bin').read_bytes()
app = (build / 'firmware.bin').read_bytes()
partitions = (build / 'partitions.bin').read_bytes()
assert merged[0x10000:] == app, 'Merged application differs from built application'
assert merged[0x8000:0x8000 + len(partitions)] == partitions
assert merged[0x9000:0x10000] == b'\xff' * 0x7000, 'NVS/PHY must not contain OTA boot_app0'
assert len(merged) <= 0x400000
for name, data in [('bootloader', merged), ('app', app)]:
    image = ESP32C3FirmwareImage(io.BytesIO(data))
    assert image.chip_id == 5, (name, image.chip_id)
    assert image.flash_mode == 2 and image.flash_size_freq == 0x2F, name
    assert image.checksum == image.calculate_checksum(), name + ' checksum'
    assert image.append_digest and image.stored_digest == image.calc_digest, name + ' SHA256'

pt = PartitionTable.from_binary(partitions)
expected = [('nvs', 1, 2, 0x9000, 0x5000), ('phy_init', 1, 1, 0xE000, 0x1000),
            ('factory', 0, 0, 0x10000, 0x3F0000)]
assert [(v.name, v.type, v.subtype, v.offset, v.size) for v in pt] == expected
assert len(app) <= pt[-1].size
args.output.mkdir(parents=True, exist_ok=True)
firmware_name = 'inkble_huawei_a1_full_0x0.bin'
shutil.copyfile(build / 'firmware_merged.bin', args.output / firmware_name)
shutil.copyfile(build / 'firmware.elf', args.output / 'inkble_huawei_a1.elf')
with zipfile.ZipFile(args.output / 'inkble-macos-sender.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((ROOT / 'sender').iterdir()):
        if path.is_file() and path.suffix in ('.py', '.txt', '.md', '.png'):
            archive.write(path, 'inkble-macos-sender/' + path.name)
    archive.write(ROOT / 'PROTOCOL.md', 'inkble-macos-sender/PROTOCOL.md')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
sources = [ROOT / name for name in ('platformio.ini', 'partitions.csv', 'README.md', 'PROTOCOL.md',
                                   'LICENSE', 'NOTICE.md', 'requirements-dev.txt')]
for folder in ('src', 'sender', 'tools', 'tests'):
    sources.extend(p for p in (ROOT / folder).rglob('*')
                   if p.is_file() and not any(part.startswith('.') or part == '__pycache__'
                                              for part in p.relative_to(ROOT).parts)
                   and p.suffix in ('.py', '.cpp', '.h', '.md', '.txt', '.png', '.json', '.gz'))
manifest = {
    'hardware': 'Huawei A1', 'chip': 'ESP32-C3', 'flash': 'DIO / 80 MHz / 4 MB',
    'flash_offset': '0x0', 'image_size': [768, 552], 'frame_bytes': 105984,
    'platform': 'espressif32@6.12.0', 'framework': 'Arduino ESP32 2.0.17', 'nimble': '2.5.1',
    'checks': ['ESP32-C3 bootloader and application checksums and SHA256 verified',
               'Merged application equals build output', 'Factory partition table and MD5 verified',
               'NVS/PHY ranges erased; no OTA metadata image'],
    'hardware_tested': False,
    'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)},
    'artifacts': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in (
        args.output / firmware_name, args.output / 'inkble-macos-sender.zip')},
}
(args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
(args.output / 'SHA256SUMS').write_text(''.join(f'{v["sha256"]}  {k}\n' for k, v in manifest['artifacts'].items()))
print(json.dumps(manifest['artifacts'], indent=2))
print('Verified: ESP32-C3, DIO/80MHz/4MB, factory app at 0x10000; flash merged image at 0x0.')
