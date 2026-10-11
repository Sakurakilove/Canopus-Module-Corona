#!/bin/sh
# Non-installable core/I/O objects. Never bypass Canopus's withdrawal policy.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SDK=${CANOPUS_ROOT:-"$ROOT/../Canopus"}
CLANG=${CLANG:-clang}
OUT="$ROOT/build/p65-offline-audit"
FIRMWARE=${CANOPUS_P65_FIRMWARE:?Set CANOPUS_P65_FIRMWARE to the exact P65 AP or full OTA}
python3 "$SDK/scripts/audit_p65_firmware.py" "$FIRMWARE" > /dev/null
mkdir -p "$OUT"
for name in resource_hook config platform_p65_io platform_p65_fs platform_p65_cache; do
    "$CLANG" --target=arm-none-eabi -mcpu=cortex-m33 -mthumb -mfloat-abi=soft \
        -Os -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables \
        -Wall -Wextra -Werror -DRH_TARGET_P65=1 -DCANOPUS_SUP_P65_RESIDENT=1 \
        -I"$ROOT/include" -I"$SDK/manager/target/p65" \
        -I"$SDK/targets/xiaomi-p65-3.100.043/generated" \
        -c "$ROOT/src/$name.c" -o "$OUT/$name.o"
done
printf 'P65 offline core and I/O compiled; no installer or native Resource Hook module produced.\n'
