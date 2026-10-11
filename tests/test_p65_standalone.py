"""Execute the standalone Thumb component with real AP read/write/FS/cache code.

ROM register_driver, fd tables, underlying files and cache retirement are
modeled. No device access and no claim about cold boot or automatic repaint.
Build with scripts/build-p65-standalone.sh first; objects must match sources.
"""
import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest
import zipfile
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_CODE
from unicorn.arm_const import *

ROOT=Path(__file__).resolve().parents[1]
SDK=Path(os.environ.get('CANOPUS_ROOT',ROOT.parent/'Canopus'))
PROJECT=Path(os.environ.get('RW6_PROJECT_ROOT',str(ROOT.parent.parent)))
BUILD=ROOT/'build/p65-standalone'
spec=importlib.util.spec_from_file_location('exact_ap',SDK/'scripts/tests/test_p65_firmware_io.py')
ap=importlib.util.module_from_spec(spec);spec.loader.exec_module(ap)


class Machine:
    BUFFER=0x20001000;PAIR=0x20003000;STOP=0x20004000;ERRNO=0x20006000;STACK=0x2007f000
    DRIVER=0x3c4501d0;CONTROL=0x3c421000;INODE=0x3c421100
    args=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    saved=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)

    def __init__(self,sections,symbols,files,relocations=()):
        self.u=u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
        u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M33)
        image=ap.firmware_bytes();u.mem_map(0xc0c0000,(len(image)+4095)&~4095);u.mem_write(0xc0c0000,image)
        u.mem_map(0x3c000000,0x500000)
        start=0xc0efdc4-0xc0c0000;u.mem_write(0x3c000000,image[start:start+0x3d2080])
        u.mem_map(0x20000000,0x80000)
        u.mem_map(0x1c000000,0x3d3000)
        u.mem_write(0x1c000000,image[start:start+0x3d2080])
        for address,data in sections:u.mem_write(address,data)
        self.symbols=symbols;self.files=dict(files);self.fds={};self.opens=[];self.closes=[]
        self.cache=[];self.gets=self.puts=0;self.register_calls=[];self.register_rc=0
        self.endpoint_exists=False;self.close_error=False;self.read_limit=None
        self.ops=0
        u.mem_write(self.DRIVER,struct.pack('<13I',ord('/'),0,0,0xc7357d5,0xc735789,
            0xc735739,0xc7356e9,0xc73589d,0xc735691,0,0,0,0))
        self.word(0x3c45012c,0x3c430000);self.word(0x3c450130,0x3c430100)
        self.hook(0x1c15a954,self.register) # AP veneer is executed, ROM leaf modeled.
        self.hook(0xc247ea8,self.open_file)
        self.hook(0xc244b60,self.close_file)
        self.hook(0x1c154d9c,self.close_file)
        self.hook(0x1c1580e4,self.open_file)
        self.hook(0xc2444c4,self.get_file)
        self.hook(0xc244560,self.put_file)
        self.hook(0xc25823c,lambda:self.ERRNO)
        self.hook(0x1c154700,self.get_file)
        self.hook(0x1c15479c,self.put_file)
        self.hook(0x1c168478,lambda:self.ERRNO)
        self.hook(0xc4f793c,lambda:self.ERRNO)
        self.hook(0x20005000,self.read_file)
        self.hook(0x20005010,self.write_file)
        self.hook(0xc741a50,self.format_path)
        self.hook(0xc8bef00,self.open_file)
        self.hook(0xc73e32c,lambda:0)
        self.hook(0xc73baa8,self.drop_cache)
        self.relocation_count=0
        for record,symbol,destination in relocations:
            self.u.mem_write(self.BUFFER,record);self.u.mem_write(self.BUFFER+32,symbol)
            assert self.invoke(0xc4f84c5,(self.BUFFER,self.BUFFER+32,destination))==0
            self.relocation_count+=1

    def reg(self,n):return self.u.reg_read(self.args[n])
    def word(self,address,value=None):
        if value is not None:self.u.mem_write(address,struct.pack('<I',value&0xffffffff))
        return struct.unpack('<I',self.u.mem_read(address,4))[0]
    def string(self,address):
        data=bytes(self.u.mem_read(address,256));return data.split(b'\0',1)[0].decode()
    def hook(self,address,callback):
        def run(u,pc,size,user):
            value=callback()
            for r in (*self.args[1:],UC_ARM_REG_R12):u.reg_write(r,0xdeadbeef)
            u.reg_write(UC_ARM_REG_R0,value&0xffffffff)
            u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
        if not hasattr(self,'hooks'):self.hooks={}
        self.hooks[address]=self.u.hook_add(UC_HOOK_CODE,run,None,address,address)
    def invoke(self,entry,values=()):
        for i,r in enumerate(self.args):self.u.reg_write(r,values[i] if i<len(values) else 0)
        for i,r in enumerate(self.saved):self.u.reg_write(r,0x34560000+i)
        self.u.reg_write(UC_ARM_REG_SP,self.STACK);self.u.reg_write(UC_ARM_REG_LR,self.STOP|1)
        self.u.emu_start(self.symbols[entry] if isinstance(entry,str) else entry,self.STOP,count=30000000)
        assert self.u.reg_read(UC_ARM_REG_PC)==self.STOP
        assert self.u.reg_read(UC_ARM_REG_SP)==self.STACK
        for i,r in enumerate(self.saved):assert self.u.reg_read(r)==0x34560000+i
        value=self.reg(0);return value if value<0x80000000 else value-0x100000000
    def register(self):
        path,ops,permissions,private=(self.string(self.reg(0)),self.reg(1),self.reg(2),self.reg(3))
        self.register_calls.append((path,ops,permissions,private));self.ops=ops
        self.endpoint_exists=self.register_rc==0
        return self.register_rc
    def open_file(self):
        path=self.string(self.reg(0));flags=self.reg(1);permissions=self.reg(2)
        self.opens.append((path,flags,permissions))
        if path=='/dev/rw6-corona-v1' and self.endpoint_exists:
            data=b''
        elif path in self.files:data=self.files[path]
        else:self.word(self.ERRNO,2);return -1
        fd=0
        while fd in self.fds:fd+=1
        file=0x3c420000+fd*64;inode=0x3c420800+fd*32;ops=0x3c420c00+fd*32
        self.fds[fd]={'path':path,'data':data,'position':0,'file':file}
        self.word(file,flags&3);self.word(file+16,inode);self.word(inode+16,ops)
        self.word(ops+8,0x20005001);self.word(ops+12,0x20005011)
        return fd
    def close_file(self):
        fd=self.reg(0);item=self.fds.pop(fd,None)
        if item is None:return -9
        self.closes.append(item['path']);return -1 if self.close_error else 0
    def get_file(self):
        item=self.fds.get(self.reg(0));self.gets+=1
        if item is None:return -9
        self.word(self.reg(1),item['file']);return 0
    def put_file(self):self.puts+=1;return 0
    def read_file(self):
        file,buffer,count=[self.reg(i) for i in range(3)]
        item=next(v for v in self.fds.values() if v['file']==file)
        if self.read_limit:count=min(count,self.read_limit)
        data=item['data'][item['position']:item['position']+count]
        if data:self.u.mem_write(buffer,data)
        item['position']+=len(data);return len(data)
    def write_file(self):
        file,buffer,count=[self.reg(i) for i in range(3)]
        item=next(v for v in self.fds.values() if v['file']==file)
        data=bytes(self.u.mem_read(buffer,count));at=item['position']
        item['data']=item['data'][:at]+data+item['data'][at+count:]
        self.files[item['path']]=item['data'];item['position']+=count
        return count
    def format_path(self):
        dst,capacity,fmt,source=[self.reg(i) for i in range(4)]
        assert self.string(fmt)=='/%s'
        value=('/'+self.string(source)).encode()
        assert len(value)<capacity
        self.u.mem_write(dst,value+b'\0');return len(value)
    def drop_cache(self):
        cache,key,userdata=[self.reg(i) for i in range(3)]
        offset=0 if cache==0x3c430100 else 4
        self.cache.append((cache,self.string(self.word(key+offset)),self.word(key+offset+4),userdata))
        return 0
    def init(self):return self.invoke('rh_p65_theme_module_initialize',(self.PAIR,))
    def command(self,mode,seq=1,parts=None,magic=0x43365452,reserved=0):
        frame=struct.pack('<4I',magic,seq,mode,reserved)
        assert self.invoke('control_open',(self.CONTROL,))==0
        if parts is None:parts=[frame]
        writes=[]
        for part in parts:
            self.u.mem_write(self.BUFFER,part)
            writes.append(self.invoke('control_write',(self.CONTROL,self.BUFFER,len(part))))
        close=self.invoke('control_close',(self.CONTROL,));return writes,close
    def status(self):
        assert self.invoke('control_open',(self.CONTROL,))==0
        assert self.invoke('control_read',(self.CONTROL,self.BUFFER,48))==48
        value=struct.unpack('<12I',self.u.mem_read(self.BUFFER,48))
        assert self.invoke('control_read',(self.CONTROL,self.BUFFER,48))==0
        assert self.invoke('control_close',(self.CONTROL,))==0
        return value
    def fs_open(self,path,access=2):
        self.u.mem_write(self.BUFFER,path.encode()+b'\0')
        return self.invoke(self.word(self.DRIVER+12),(self.DRIVER,self.BUFFER,access))


class StandaloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names=('p65_standalone','p65_standalone_mem','resource_hook','platform_p65_io','platform_p65_fs','platform_p65_cache')
        objects=[]
        for name in names:
            obj=BUILD/(name+'.o');assert obj.stat().st_mtime>=(ROOT/'src'/(name+'.c')).stat().st_mtime,'Rebuild changed native source'
            objects.append(str(obj))
        artifact=BUILD/'rw6-corona.elf'
        assert artifact.stat().st_mtime>=max(Path(o).stat().st_mtime for o in objects)
        with artifact.open('rb') as f:
            elf=ELFFile(f)
            assert elf['e_type']=='ET_REL' and elf['e_entry']==1
            headers=list(elf.iter_sections());symtab=elf.get_section_by_name('.symtab')
            payload=artifact.read_bytes();m=Machine([],{},{});info=0x20007000;shdr=0x20008000
            m.u.mem_write(info,bytes(144));m.u.mem_write(info+32,payload[:52]);m.word(info+0x88,0)
            m.word(info+0x58,shdr);m.u.mem_write(shdr,payload[elf['e_shoff']:elf['e_shoff']+40*elf['e_shnum']])
            m.hook(0xc4f9ddc,lambda:0) # Headers are independently parsed from actual ELF above.
            cls.allocations=[]
            def allocate():
                alignment,size=m.reg(0),m.reg(1);base=(0x20010000,0x20050000)[len(cls.allocations)]
                assert alignment==4 and size>0
                cls.allocations.append((base,size));return base
            def read_section():
                dest,size=m.reg(1),m.reg(2);sp=m.u.reg_read(UC_ARM_REG_SP)
                offset=struct.unpack('<Q',m.u.mem_read(sp,8))[0]
                assert offset+size<=len(payload)
                m.u.mem_write(dest,payload[offset:offset+size]);return 0
            def zero():
                dest,value,size=m.reg(0),m.reg(1),m.reg(2)
                m.u.mem_write(dest,bytes([value&255])*size);return dest
            m.hook(0xc50b2c8,allocate);m.hook(0xc4f9eec,read_section);m.hook(0xc8be820,zero)
            assert m.invoke(0xc4f9b59,(info,))==0
            bases={i:m.word(shdr+40*i+12) for i,s in enumerate(headers) if s['sh_flags']&2}
            cls.sections=[(bases[i],bytes(m.u.mem_read(bases[i],s['sh_size']))) for i,s in enumerate(headers) if i in bases]
            cls.symbols={s.name:bases[s['st_shndx']]+s['st_value'] for s in symtab.iter_symbols()
                         if s.name and isinstance(s['st_shndx'],int) and s['st_shndx'] in bases}
            cls.relocations=[];raw=symtab.data()
            for section in headers:
                if section['sh_type']!='SHT_REL' or section['sh_info'] not in bases:continue
                for r in section.iter_relocations():
                    index=r['r_info_sym'];s=symtab.get_symbol(index);where=s['st_shndx']
                    if where=='SHN_ABS':value=s['st_value']
                    else:assert isinstance(where,int) and where in bases;value=bases[where]+s['st_value']
                    symbol=bytearray(raw[16*index:16*(index+1)]);struct.pack_into('<I',symbol,4,value)
                    cls.relocations.append((struct.pack('<II',r['r_offset'],r['r_info']),bytes(symbol),bases[section['sh_info']]+r['r_offset']))
            assert all(0x20010000<=a<a+len(d)<0x20070000 for a,d in cls.sections)
        cls.assets=json.loads((BUILD/'assets.json').read_text());cls.files={}
        for style in ('orbit','fold'):
            bindings=json.loads((PROJECT/(style+'-rw6')/'targets/p65-3.100.043.json').read_text())['bindings']
            with zipfile.ZipFile(PROJECT/'deliverables'/f'{style}-rw6-p65-3.100.043.crpack') as archive:
                for item in cls.assets:
                    if item['style']==style:
                        cls.files[item['destination']]=archive.read(bindings[item['role']])
                        cls.files[item['source']]=b'stock-icon'
    def machine(self):return Machine(self.sections,self.symbols,self.files,self.relocations)

    def test_real_ap_section_layout_and_every_relocation_initialize_actual_rel_artifact(self):
        m=self.machine();self.assertGreater(m.relocation_count,250)
        self.assertEqual(len(self.allocations),2);self.assertLess(self.allocations[0][1],65536)
        self.assertEqual(self.allocations[1][1],376)
        self.assertEqual(m.init(),0);self.assertEqual(m.status()[11],0x30005)

    def test_native_initializer_writes_stage_and_registration_error_to_precreated_marker(self):
        path='/data/quickapp/files/ng.lst.corona/rw6-init-v2.status'
        for code in (0,-12):
            m=self.machine();m.files[path]=bytes(16);m.register_rc=code
            self.assertEqual(m.init(),0)
            self.assertEqual(struct.unpack('<IIIi',m.files[path]),(0x324e3652,1,5,code))
            self.assertEqual(m.fds,{})
        m=self.machine();m.files[path]=bytes(16);m.word(m.DRIVER+24,0)
        self.assertEqual(m.init(),-212)
        self.assertEqual(struct.unpack('<IIIi',m.files[path]),(0x324e3652,1,2,-212))

    def test_compact_snapshots_redirect_every_exact_path_and_alias_for_both_styles(self):
        m=self.machine();self.assertEqual(m.init(),0)
        for mode,style in ((1,'orbit'),(2,'fold')):
            self.assertEqual(m.command(mode,mode)[1],0)
            for asset in self.assets:
                if asset['style']!=style:continue
                fdplusone=m.fs_open(asset['source'][1:]);self.assertGreater(fdplusone,0)
                self.assertEqual(m.opens[-1][0],asset['destination'])
                self.assertEqual(m.invoke('rh_p65_io_close',(fdplusone-1,)),0)
        self.assertEqual(m.status()[4:6],(102,0));self.assertEqual(m.fds,{})

    def test_init_registers_only_control_endpoint_and_never_hooks_or_frees_callback_code(self):
        m=self.machine();self.assertEqual(m.init(),0)
        self.assertEqual(m.register_calls[0][0],'/dev/rw6-corona-v1')
        self.assertEqual(m.register_calls[0][2:],(0o600,0))
        self.assertEqual(m.word(m.DRIVER+12),0xc7357d5)
        self.assertEqual(m.invoke(m.word(m.PAIR),(0,)),-16)
        self.assertEqual(m.status()[:4],(0x48543652,1,0,0))

    def test_wrong_identity_or_driver_never_registers_or_changes_callbacks(self):
        for kind in ('version','build','driver'):
            m=self.machine()
            if kind=='version':m.u.mem_write(0xc3bf9fd,b'3.100.044')
            elif kind=='build':m.u.mem_write(0xcbff458,b'wrong')
            else:m.word(m.DRIVER+24,0)
            before=bytes(m.u.mem_read(m.DRIVER,52))
            self.assertLess(m.init(),0);self.assertEqual(m.register_calls,[])
            self.assertEqual(bytes(m.u.mem_read(m.DRIVER,52)),before)
            self.assertEqual(m.word(m.PAIR),0)

    def test_existing_endpoint_is_not_replaced(self):
        m=self.machine();m.endpoint_exists=True
        self.assertEqual(m.init(),-217);self.assertEqual(m.register_calls,[])
        self.assertEqual(m.word(m.PAIR),0)

    def test_registration_error_still_retains_potentially_escaped_callbacks(self):
        m=self.machine();m.register_rc=-12
        self.assertEqual(m.init(),0)
        self.assertEqual(m.invoke(m.word(m.PAIR),(0,)),-16)
        self.assertEqual(m.status()[9],0xfffffff4)
        self.assertEqual(m.word(m.DRIVER+12),0xc7357d5)

    def test_orbit_fold_stock_switches_keep_native_sizes_validate_all_files_and_drop_exact_keys(self):
        m=self.machine();self.assertEqual(m.init(),0)
        for seq,mode in enumerate((1,2,0),1):
            self.assertEqual(m.command(mode,seq),([16],0))
            s=m.status();self.assertEqual((s[2],s[6],s[7],s[8]),(mode,seq,0,seq))
            self.assertEqual(len(m.cache),102*seq)
            for cache,path,type_,userdata in m.cache[-102:]:
                self.assertIn(path,{r['source'] for r in self.assets});self.assertEqual((type_,userdata),(1,0))
            self.assertGreater(m.fs_open('resource/app/launcher/music.bin'),0)
            expected='/resource/app/launcher/music.bin' if mode==0 else '/data/quickapp/files/ng.lst.corona/themes/rw6-'+('orbit' if mode==1 else 'fold')+'-v1/music.bin'
            self.assertEqual(m.opens[-1][0],expected)
        self.assertEqual(m.status()[4],2)
        self.assertEqual(m.gets,m.puts)
        self.assertEqual(m.invoke(m.word(m.PAIR),(0,)),-16)

    def test_short_read_transfers_are_completed_and_every_preflight_handle_is_closed(self):
        m=self.machine();m.init();m.read_limit=113
        self.assertEqual(m.command(1),([16],0));self.assertEqual(m.fds,{})
        self.assertEqual(len(m.closes),108);self.assertEqual(m.gets,m.puts)

    def test_missing_corrupt_truncated_or_extended_asset_keeps_previous_mode_and_hook(self):
        target=next(r['destination'] for r in self.assets if r['style']=='fold')
        for kind in ('missing','corrupt','truncated','extended'):
            m=self.machine();m.init();self.assertEqual(m.command(1),([16],0))
            value=m.files[target]
            if kind=='missing':del m.files[target]
            elif kind=='corrupt':m.files[target]=bytes([value[0]^1])+value[1:]
            elif kind=='truncated':m.files[target]=value[:-1]
            else:m.files[target]=value+b'x'
            cache=len(m.cache);self.assertLess(m.command(2,2)[1],0)
            status=m.status();self.assertEqual((status[2],status[6],status[8]),(1,2,1))
            self.assertNotEqual(status[7],0);self.assertEqual(len(m.cache),cache)
            self.assertEqual(m.fds,{})

    def test_close_failure_does_not_install_or_publish_theme(self):
        m=self.machine();m.init();m.close_error=True
        self.assertEqual(m.command(1),([16],-5))
        self.assertEqual(m.word(m.DRIVER+12),0xc7357d5)
        self.assertEqual(m.status()[2],0)

    def test_bad_frames_and_partial_or_overlong_packets_never_install(self):
        cases=[{'mode':3},{'mode':1,'seq':0},{'mode':1,'magic':0},{'mode':1,'reserved':1},
            {'mode':1,'parts':[b'short']},{'mode':1,'parts':[bytes(17)]}]
        for case in cases:
            m=self.machine();m.init();self.assertLess(m.command(**case)[1],0)
            self.assertEqual(m.word(m.DRIVER+12),0xc7357d5);self.assertEqual(m.cache,[])

    def test_fragmented_control_writes_apply_only_after_close(self):
        m=self.machine();m.init();frame=struct.pack('<4I',0x43365452,7,1,0)
        self.assertEqual(m.invoke('control_open',(m.CONTROL,)),0)
        for start,end in ((0,3),(3,11),(11,16)):
            m.u.mem_write(m.BUFFER,frame[start:end])
            self.assertEqual(m.invoke('control_write',(m.CONTROL,m.BUFFER,end-start)),end-start)
            self.assertEqual(m.word(m.DRIVER+12),0xc7357d5)
        self.assertEqual(m.invoke('control_close',(m.CONTROL,)),0)
        self.assertEqual(m.status()[6],7)

    def test_control_contexts_are_bounded_independent_and_released_on_close(self):
        m=self.machine();m.init()
        for i in range(4):self.assertEqual(m.invoke('control_open',(m.CONTROL+32*i,)),0)
        self.assertEqual(m.invoke('control_open',(m.CONTROL+128,)),-24)
        self.assertEqual(m.invoke('control_open',(m.CONTROL,)),-16)
        self.assertEqual(m.invoke('control_read',(0,m.BUFFER,48)),-9)
        for i in range(4):self.assertEqual(m.invoke('control_close',(m.CONTROL+32*i,)),0)
        self.assertEqual(m.invoke('control_open',(m.CONTROL+128,)),0)
        self.assertEqual(m.invoke('control_close',(m.CONTROL+128,)),0)

    def test_hook_falls_back_when_staged_file_disappears_and_does_not_redirect_write(self):
        m=self.machine();m.init();m.command(1)
        path='/data/quickapp/files/ng.lst.corona/themes/rw6-orbit-v1/music.bin';del m.files[path]
        self.assertGreater(m.fs_open('resource/app/launcher/music.bin'),0)
        self.assertEqual(m.opens[-1][0],'/resource/app/launcher/music.bin')
        self.assertEqual(m.status()[5],1)
        self.assertGreater(m.fs_open('resource/app/launcher/music.bin',1),0)
        self.assertEqual(m.opens[-1][0],'/resource/app/launcher/music.bin')
        self.assertEqual(m.status()[4],0)

    def test_foreign_hook_or_uninitialized_cache_is_rejected_without_pointer_overwrite(self):
        for kind in ('hook','cache'):
            m=self.machine();m.init()
            if kind=='hook':m.word(m.DRIVER+12,0x20005001)
            else:m.word(0x3c45012c,0)
            before=m.word(m.DRIVER+12)
            self.assertLess(m.command(1)[1],0)
            self.assertEqual(m.word(m.DRIVER+12),before);self.assertEqual(m.status()[2],0)

    def test_open_session_survives_stock_copy_from_stack_file_to_descriptor(self):
        m=self.machine();self.assertEqual(m.init(),0)
        temporary=m.CONTROL;descriptor=m.CONTROL+128
        self.assertEqual(m.invoke('control_open',(temporary,)),0)
        context=m.word(temporary+20);self.assertNotEqual(context,0)
        m.u.mem_write(descriptor,bytes(m.u.mem_read(temporary,32)))
        m.u.mem_write(temporary,bytes([0xa5])*32) # Stack storage is reused.
        self.assertEqual(m.invoke('control_read',(descriptor,m.BUFFER,48)),48)
        self.assertEqual(m.word(m.BUFFER+44),0x30005)
        self.assertEqual(m.invoke('control_close',(descriptor,)),0)
        self.assertEqual(m.word(descriptor+20),0)
        # Four cycles of reused temporary storage must not exhaust clients.
        for _ in range(8):
            self.assertEqual(m.invoke('control_open',(temporary,)),0)
            m.u.mem_write(descriptor,bytes(m.u.mem_read(temporary,32)))
            m.u.mem_write(temporary,bytes([0xa5])*32)
            self.assertEqual(m.invoke('control_close',(descriptor,)),0)

    def test_real_ap_write_dispatch_uses_correct_control_fops_slot(self):
        m=self.machine();m.init();self.assertEqual(m.invoke('control_open',(m.CONTROL,)),0)
        m.word(m.CONTROL,2);m.word(m.CONTROL+16,m.INODE);m.word(m.INODE+16,m.ops)
        m.fds[7]={'path':'control','data':b'','position':0,'file':m.CONTROL}
        frame=struct.pack('<4I',0x43365452,9,1,0);m.u.mem_write(m.BUFFER,frame)
        self.assertEqual(m.invoke(0xc8be041,(7,m.BUFFER,16)),16)
        self.assertEqual(m.word(m.DRIVER+12),0xc7357d5)
        del m.fds[7];self.assertEqual(m.invoke('control_close',(m.CONTROL,)),0)
        self.assertEqual(m.status()[6],9)


if __name__=='__main__':unittest.main()
