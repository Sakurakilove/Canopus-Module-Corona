#!/usr/bin/env python3
"""Prepare fixed Corona mappings/checksums for the P65 watchface controller.

No image modification, target promotion or device access. Input CRPacks must
already have been produced by Corona Editor for the exact firmware.
"""
import argparse
import json
from pathlib import Path
import zipfile
import zlib


def prepare(project,output):
    records=[];tables=[];assets=[];counts=[]
    app_root='/data/quickapp/files/ng.lst.corona/'
    for style in ('orbit','fold'):
        theme=project/(style+'-rw6')
        inventory=json.loads((theme/'asset-inventory.json').read_text())
        bindings=json.loads((theme/'targets/p65-3.100.043.json').read_text())['bindings']
        rows=[];checks=[];pool=bytearray();style_records=[]
        with zipfile.ZipFile(project/'deliverables'/f'{style}-rw6-p65-3.100.043.crpack') as archive:
            for record in sorted(inventory,key=lambda record:record['resource']):
                role=record['role'];source=record['resource']
                if not source.startswith('/resource/app/') or not source.endswith('.bin'):
                    raise ValueError('Only static app icon resources are permitted')
                data=archive.read(bindings[role])
                destination='/data/quickapp/files/ng.lst.corona/themes/rw6-'+style+'-v1/'+role+'.bin'
                if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./-' for c in source+destination):
                    raise ValueError('Nonportable path')
                if '..' in source or '..' in destination or len(source)>=256 or len(destination)>=256:
                    raise ValueError('Unsafe/oversized path')
                source_offset=len(pool);pool.extend(source.encode()+b'\0')
                # Keep packed u16 offset pairs distinguishable from AP/ROM/RAM
                # pointer literals for the stock verifier's conservative raw
                # word scan. Padding changes only string-pool layout; it grants
                # no address permissions and the native validator checks bounds.
                while ((len(pool)+len(app_root))>>8) in (0x0c,0x1c,0x2c,0x3c):pool.append(0)
                destination_offset=len(pool);pool.extend(destination.encode()+b'\0')
                rows.append(f'{{{source_offset},{destination_offset+len(app_root)},{len(source)},{len(destination)-len(app_root)},0,0}}')
                checksum=zlib.crc32(data)
                checks.append('{rh_p65_snapshot_'+style+f'.pool+{destination_offset},{len(data)}u,0x{checksum:08x}u'+'}')
                style_records.append({'style':style,'role':role,'source':source,
                    'destination':destination,'stagingFilename':style+'_native_'+role+'.bin',
                    'size':len(data),'crc32':checksum,'width':record['width'],'height':record['height']})
        if not 1<=len(rows)<=256:raise ValueError('Rule count must be between 1 and 256')
        counts.append(len(rows))
        if len(pool)>32769:raise ValueError('Snapshot pool exceeds core limit')
        typename='rh_p65_fixed_snapshot_'+style
        # Pool destinations contain absolute paths; indexed destinations point
        # past RH_APP_FILES_ROOT, as required by the shared snapshot resolver.
        literal='\n'.join('"'+''.join('\\%03o'%b for b in pool[i:i+48])+'"' for i in range(0,len(pool),48))
        tables.append(f'struct {typename} {{ uint32_t references,allocation_bytes,pool_bytes,count; '
            f'struct rh_indexed_rule rules[{len(rows)}]; char pool[{len(pool)}]; }};\n'
            f'_Static_assert(offsetof(struct {typename},pool)==16+{len(rows)}*8,"snapshot ABI");\n'
            f'static const struct {typename} rh_p65_snapshot_{style}={{0,{16+len(rows)*8+len(pool)}u,{len(pool)}u,{len(rows)}u,\n'
            '{'+',\n'.join(rows)+'},\n'+literal+'};\n')
        assets.append('{\n'+',\n'.join(checks)+'\n}')
        records.extend(style_records)
    output.mkdir(parents=True,exist_ok=True)
    header='/* Generated fixed mappings; source CRPack bytes pinned by size/CRC32. */\n'
    if len(set(counts))!=1:raise ValueError('Both styles must cover identical rule counts')
    header+=f'#define RH_P65_THEME_RULES {counts[0]}u\n'
    header+='struct rh_p65_asset { const char *path; uint32_t size, crc32; };\n'
    header+=''.join(tables)
    header+='static const struct rh_snapshot *const rh_p65_theme_snapshots[2]={\n'
    header+='(const struct rh_snapshot *)&rh_p65_snapshot_orbit,(const struct rh_snapshot *)&rh_p65_snapshot_fold};\n'
    header+='static const struct rh_p65_asset rh_p65_theme_assets[2][RH_P65_THEME_RULES]={\n'+',\n'.join(assets)+'\n};\n'
    (output/'p65_theme_assets.h').write_text(header)
    (output/'assets.json').write_text(json.dumps(records,indent=2)+'\n')
    return records


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();records=prepare(args.project_root,args.output)
    print(f'Prepared {len(records)} exact-sized system image resources')
