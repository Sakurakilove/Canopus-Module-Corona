#!/usr/bin/env python3
"""Build the exact-RW6 Corona manager RPK; themes are separate CRPacks."""
from pathlib import Path
import argparse,json,subprocess,shutil
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=root/'build/p65-manager/app')
args=parser.parse_args();manager=root/'manager';out=args.output.resolve()
out.mkdir(parents=True,exist_ok=True)
profile=manager/'src/ts/runtime-profile.ts';manifest=manager/'src/manifest.json';saved=[p.read_bytes() for p in (profile,manifest)]
try:
 profile.write_text('export const RUNTIME_TARGET = "xiaomi-p65-3.100.043" as string;\nexport const STATIC_ICONS_ONLY = true as boolean;\nexport const RUNTIME_HINT = "切换后重新打开系统页面" as string;\n')
 m=json.loads(saved[1]);m.update(name='Corona RW6',versionName='1.3.4-p65',versionCode=12);manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 subprocess.run(['npm','run','build'],cwd=manager,check=True)
 rpk=list((manager/'dist').glob('*.rpk'));assert len(rpk)==1,rpk
 shutil.copyfile(rpk[0],out/'Corona-Manager-RW6.rpk')
finally:
 for p,data in zip((profile,manifest),saved):p.write_bytes(data)
print(out/'Corona-Manager-RW6.rpk')
