#!/usr/bin/env python3
"""Check stock ELF entry, no imports/ignored ctors and pinned P65 identity."""
from pathlib import Path
import hashlib,json,sys
from elftools.elf.elffile import ELFFile
p=Path(sys.argv[1]);b=p.read_bytes()
with p.open('rb') as f:
 e=ELFFile(f);assert e['e_type']=='ET_REL' and e['e_machine']=='EM_ARM' and e['e_entry']==1
 table=e.get_section_by_name('.symtab');undefined=[s.name for s in table.iter_symbols() if s.name and s['st_shndx']=='SHN_UNDEF'];assert not undefined,undefined
 for name in ('.init_array','.fini_array'):assert not e.get_section_by_name(name) or e.get_section_by_name(name).data_size==0
 assert b'xiaomi-p65-3.100.043' in b
 report={'target':'xiaomi-p65-3.100.043','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'entry':1,'sections':e.num_sections(),'imports':undefined,'scope':'static icons; native Canopus descriptor; QuickApp file control','deviceTested':False,'systemAutostartImplemented':False}
 assert report['sections']<=20
(p.parent/'build-info.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
