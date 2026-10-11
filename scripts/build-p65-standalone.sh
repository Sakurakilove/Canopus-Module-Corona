#!/bin/sh
# Build the separate manually controlled P65 icon component. Old Supervisor and
# the full Resource Hook target guard remain unchanged.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SDK=${CANOPUS_ROOT:-"$ROOT/../Canopus"}
CC=${CLANG:-clang}
LD=${LD_LLD:-ld.lld}
OUT="$ROOT/build/p65-standalone"
PROJECT=${RW6_PROJECT_ROOT:?Set RW6_PROJECT_ROOT to the theme project/delivery root}
FIRMWARE=${CANOPUS_P65_FIRMWARE:?Set CANOPUS_P65_FIRMWARE to the exact AP/OTA}
python3 "$SDK/scripts/audit_p65_firmware.py" "$FIRMWARE" >/dev/null
python3 "$ROOT/scripts/prepare-p65-standalone-assets.py" --project-root "$PROJECT" --output "$OUT"
OBJECTS=""
for name in p65_standalone p65_standalone_mem resource_hook platform_p65_io platform_p65_fs platform_p65_cache;do
    "$CC" --target=arm-none-eabi -mcpu=cortex-m33 -mthumb -mfloat-abi=soft \
        -Os -ffunction-sections -fdata-sections -ffreestanding -fno-builtin -fno-common -fno-jump-tables \
        -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
        -Wall -Wextra -Werror -DRH_TARGET_P65=1 -DCANOPUS_SUP_P65_RESIDENT=1 \
        -I"$ROOT/include" -I"$OUT" -I"$SDK/manager/target/p65" \
        -I"$SDK/targets/xiaomi-p65-3.100.043/generated" \
        -c "$ROOT/src/$name.c" -o "$OUT/$name.o"
    OBJECTS="$OBJECTS $OUT/$name.o"
done
"$LD" -r --gc-sections -T "$ROOT/scripts/p65_standalone_sections.ld" \
    -e rh_p65_theme_module_initialize $OBJECTS -o "$OUT/rw6-corona.elf"
python3 "$ROOT/scripts/verify-p65-standalone.py" "$OUT/rw6-corona.elf" --sdk "$SDK" --output "$OUT"
