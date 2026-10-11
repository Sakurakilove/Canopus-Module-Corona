#!/bin/sh
# Full Canopus descriptor + QuickApp management control, P65 static icons.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SDK=${CANOPUS_ROOT:-"$ROOT/../Canopus"}
OUT="$ROOT/build/p65-manager"
CC=${CLANG:-clang}
LD=${LD_LLD:-ld.lld}
python3 "$SDK/scripts/audit_p65_firmware.py" "${CANOPUS_P65_FIRMWARE:?Set firmware path}" >/dev/null
mkdir -p "$OUT"
python3 - "$ROOT" "$OUT" <<'PY'
import json,pathlib,sys
root,out=map(pathlib.Path,sys.argv[1:]);rows=json.loads((root/'resources/p65-icon-sources.json').read_text())
if not rows or len(rows)!=len(set(rows)) or any(not p.startswith('/resource/app/') or not p.endswith('.bin') for p in rows):raise ValueError('Invalid P65 cache source paths')
(out/'p65_icon_sources.h').write_text('#define RH_P65_ICON_SOURCE_COUNT '+str(len(rows))+'u\nstatic const char *const rh_p65_icon_sources[]={\n'+',\n'.join(json.dumps(p) for p in rows)+'\n};\n')
PY
OBJECTS=""
for name in module resource_hook config launcher_background platform_p65_manager platform_p65_io platform_p65_fs platform_p65_cache p65_standalone_mem; do
 "$CC" --target=arm-none-eabi -mcpu=cortex-m33 -mthumb -mfloat-abi=soft -Os \
 -ffunction-sections -fdata-sections -ffreestanding -fno-builtin -fno-common -fno-jump-tables \
 -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables -Wall -Wextra -Werror \
 -DRH_TARGET_P65=1 -DCANOPUS_SUP_P65_RESIDENT=1 -I"$ROOT/include" -I"$OUT" \
 -I"$SDK/sdk/c" -I"$SDK/manager/target/p65" -I"$SDK/targets/xiaomi-p65-3.100.043/generated" \
 -c "$ROOT/src/$name.c" -o "$OUT/$name.o"
 OBJECTS="$OBJECTS $OUT/$name.o"
done
"$CC" --target=arm-none-eabi -mcpu=cortex-m33 -mthumb -mfloat-abi=soft -Os -ffunction-sections \
 -ffreestanding -fno-builtin -fno-unwind-tables -I"$SDK/sdk/c" \
 -c "$SDK/runtime/control/canopus_control.c" -o "$OUT/control.o"
"$LD" -r --gc-sections -T "$ROOT/scripts/p65_standalone_sections.ld" \
 -e corona_p65_module_initialize $OBJECTS "$OUT/control.o" -o "$OUT/corona-p65.elf"
python3 "$ROOT/scripts/verify-p65-manager.py" "$OUT/corona-p65.elf"
