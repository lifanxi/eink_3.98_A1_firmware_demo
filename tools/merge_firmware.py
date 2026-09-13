"""Build a factory image at 0x0 using this project's single-app partition table."""
Import("env")
import os
import subprocess

# Arduino's default uploader adds OTA metadata unconditionally. This project's
# factory layout has PHY data at 0xe000, so exclude boot_app0 from uploads too.
env.Replace(FLASH_EXTRA_IMAGES=[
    (offset, path) for offset, path in env.get("FLASH_EXTRA_IMAGES", [])
    if os.path.basename(path) != "boot_app0.bin"
])

def merge(source, target, env):
    build = env.subst("$BUILD_DIR")
    esptool = os.path.join(env.PioPlatform().get_package_dir("tool-esptoolpy"), "esptool.py")
    # No OTA boot_app0 image: 0xe000 is PHY data in our factory partition table.
    subprocess.run([
        env.subst("$PYTHONEXE"), esptool, "--chip", "esp32c3", "merge_bin",
        "--flash_mode", "dio", "--flash_freq", "80m", "--flash_size", "4MB",
        "-o", os.path.join(build, "firmware_merged.bin"),
        "0x0", os.path.join(build, "bootloader.bin"),
        "0x8000", os.path.join(build, "partitions.bin"),
        "0x10000", str(target[0]),
    ], check=True)

env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", merge)
