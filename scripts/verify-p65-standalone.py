#!/usr/bin/env python3
"""Review a separate standalone icon ELF; do not modify/promote SDK targets."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import hashlib
from elftools.elf.elffile import ELFFile


def verify(artifact,sdk,output):
    with artifact.open('rb') as f:
        elf=ELFFile(f)
        if elf['e_type']!='ET_REL' or elf['e_entry']!=1:raise ValueError('Bad stock-loader entry')
        undefined=[s.name for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF']
        if undefined:raise ValueError('Unexpected imports: '+repr(undefined))
        for name in ('.init_array','.fini_array'):
            section=elf.get_section_by_name(name)
            if section is not None and section['sh_size']:raise ValueError('Unexpected constructors/destructors')
    spec=importlib.util.spec_from_file_location('probe_pack',sdk/'scripts/generate_p65_probe_pack.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    target=helper.generate(output/'standalone-targets')
    symbols=target/'symbols'
    addresses=[0x0c8bef01,0x0c8bdba9,0x0c8beaf1,0x0c8be041,0x0c4f793d,
        0x0c8bd0d1,0x0c73bca5,0x3c45012c,0x3c450130,0x3c4501dc]
    for address in addresses:
        name=f'standalone_boundary_{address:08x}'
        record={'schema':1,'symbol_id':helper.TARGET+'.'+name,'target_id':helper.TARGET,
            'name':name,'kind':'global','entry_address':hex(address),'callable_address':None,
            'instruction_set':'thumb','prototype':'component-specific audited boundary; not SDK promotion',
            'calling_convention':'arm-aapcs','contexts':{'allowed':['standalone_icon_component'],'blocking':False},
            'ownership':{'return_value':'target-specific'},'side_effects':[],
            'proof':{'static':'partial','device':'not_probed','evidence_ids':[]},
            'policy':'restricted','status':'CANDIDATE','approval_state':'PENDING',
            'provenance':{'firmware_sha256':helper.AP_SHA if hasattr(helper,'AP_SHA') else
                'a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858',
                'source':'Exact AP native I/O/cache recovery; existing four-argument P65 register_driver veneer'},
            'notes':'Scope is this separate manual icon component. Full native Manager remains withdrawn.'}
        (symbols/(helper.TARGET+'.'+name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    result=subprocess.run([str(sdk/'target/debug/canopus'),'verify',str(artifact),
        '--target',helper.TARGET,'--targets-dir',str(target.parent)],capture_output=True,text=True)
    (output/'verifier.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise ValueError(result.stdout+result.stderr)
    print(result.stdout)
    report={'artifact':artifact.name,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
        'bytes':artifact.stat().st_size,'entry':1,'undefinedImports':0,'constructors':0,
        'oldSupervisorDeploymentEnabled':False,'physicalDevice':'NEW_COMPONENT_NOT_PROBED'}
    (output/'build-info.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact',type=Path);parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();verify(args.artifact.resolve(),args.sdk.resolve(),args.output.resolve())
