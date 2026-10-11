"""Execute the compiled Corona P65 I/O port and real AP write instructions.

The downstream filesystem is modeled; this is not a device/boot validation.
Set CLANG, LD_LLD and CANOPUS_P65_FIRMWARE; requires Unicorn + pyelftools.
"""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from elftools.elf.elffile import ELFFile
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[1]
SDK = Path(os.environ.get('CANOPUS_ROOT', ROOT.parent / 'Canopus'))
spec = importlib.util.spec_from_file_location('p65_write_machine', SDK / 'scripts/tests/test_p65_firmware_io.py')
firmware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(firmware)


class NativeIoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        clang, linker = os.environ.get('CLANG', 'clang'), os.environ.get('LD_LLD', 'ld.lld')
        subprocess.run([clang, '--target=arm-none-eabi', '-mcpu=cortex-m33', '-mthumb',
            '-mfloat-abi=soft', '-Os', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-unwind-tables', '-Wall', '-Wextra', '-Werror',
            '-DCANOPUS_SUP_P65_RESIDENT=1', '-I'+str(ROOT/'include'),
            '-I'+str(SDK/'manager/target/p65'),
            '-I'+str(SDK/'targets/xiaomi-p65-3.100.043/generated'),
            '-c', str(ROOT/'src/platform_p65_io.c'), '-o', str(cls.out/'io.o')], check=True)
        subprocess.run([clang, '--target=arm-none-eabi', '-mcpu=cortex-m33', '-mthumb',
            '-mfloat-abi=soft', '-Os', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-unwind-tables', '-Wall', '-Wextra', '-Werror',
            '-I'+str(ROOT/'include'), '-c', str(ROOT/'src/platform_p65_fs.c'),
            '-o', str(cls.out/'fs.o')], check=True)
        subprocess.run([clang, '--target=arm-none-eabi', '-mcpu=cortex-m33', '-mthumb',
            '-mfloat-abi=soft', '-Os', '-ffreestanding', '-fno-builtin',
            '-fno-stack-protector', '-fno-unwind-tables', '-Wall', '-Wextra', '-Werror',
            '-I'+str(ROOT/'include'), '-c', str(ROOT/'src/platform_p65_cache.c'),
            '-o', str(cls.out/'cache.o')], check=True)
        subprocess.run([linker, '-Ttext=0x20010000', '--entry=rh_p65_io_identity',
            str(cls.out/'io.o'), str(cls.out/'fs.o'), str(cls.out/'cache.o'),
            *cls.compile_core(clang), '-o', str(cls.out/'io.elf')], check=True)
        with (cls.out/'io.elf').open('rb') as f:
            elf = ELFFile(f)
            cls.sections = [(s['sh_addr'], s.data()) for s in elf.iter_sections()
                            if s['sh_flags'] & 2 and s['sh_type'] != 'SHT_NOBITS']
            cls.symbols = {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()
                           if s.name.startswith('rh_p65_')}

    @classmethod
    def compile_core(cls,clang):
        objects=[]
        for name in ('resource_hook','config'):
            output=cls.out/(name+'.o')
            subprocess.run([clang,'--target=arm-none-eabi','-mcpu=cortex-m33','-mthumb',
                '-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin',
                '-fno-stack-protector','-fno-unwind-tables','-DRH_TARGET_P65=1',
                '-I'+str(ROOT/'include'),'-c',str(ROOT/'src'/(name+'.c')),
                '-o',str(output)],check=True)
            objects.append(str(output))
        return objects

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def machine(self, **kw):
        machine = firmware.WriteMachine(**kw)
        for address, data in self.sections: machine.u.mem_write(address, data)
        return machine

    def invoke(self, machine, name, values=()):
        u = machine.u
        for i,r in enumerate(machine.args): u.reg_write(r, values[i] if i<len(values) else 0xAABBCCDD)
        for i,r in enumerate(machine.saved): u.reg_write(r, 0x34560000+i)
        u.reg_write(UC_ARM_REG_SP, machine.STACK)
        u.reg_write(UC_ARM_REG_LR, machine.STOP|1)
        u.emu_start(self.symbols['rh_p65_io_'+name], machine.STOP, count=10000)
        self.assertEqual(u.reg_read(UC_ARM_REG_PC), machine.STOP)
        self.assertEqual(u.reg_read(UC_ARM_REG_SP), machine.STACK)
        for i,r in enumerate(machine.saved): self.assertEqual(u.reg_read(r),0x34560000+i)
        value = machine.reg(0)
        return value-0x100000000 if value>=0x80000000 else value

    def test_compiled_write_runs_real_ap_and_preserves_short_transfer_offsets(self):
        machine = self.machine(limit=3)
        used = 0
        while used < len(machine.payload):
            count = machine.call(self.symbols['rh_p65_io_write'], offset=used)
            self.assertGreater(count,0)
            used += count
        self.assertEqual(machine.writes,[(0,b'reg'),(3,b'ist'),(6,b'ry')])

    def test_wrong_runtime_identity_never_reaches_file_io(self):
        machine = self.machine()
        machine.u.mem_write(0x0C3BF9FD,b'3.100.044')
        self.assertEqual(machine.call(self.symbols['rh_p65_io_write']),-1)
        self.assertEqual(machine.writes,[])
        self.assertEqual(machine.gets,0)

    def test_open_supplies_owner_permissions_and_accepts_descriptor_zero(self):
        machine = self.machine(); captured=[]
        def opened():
            captured.append([machine.reg(i) for i in range(3)])
            return 0
        machine.hook(0x0C8BEF00,opened)
        self.assertEqual(self.invoke(machine,'open',(machine.BUFFER,0x26)),0)
        self.assertEqual(captured,[[machine.BUFFER,0x26,0o600]])

    def test_null_buffer_and_wrong_identity_are_rejected_before_dispatch(self):
        machine=self.machine()
        self.assertEqual(self.invoke(machine,'write',(7,0,4)),-1)
        self.assertEqual(self.invoke(machine,'read',(7,0,4)),-1)
        self.assertEqual(machine.gets,0)

    def test_ap_write_error_preserves_errno_and_reference_balance(self):
        machine=self.machine(driver_error=-5)
        self.assertEqual(machine.call(self.symbols['rh_p65_io_write']),-1)
        self.assertEqual(machine.word(machine.ERRNO),5)
        self.assertEqual((machine.gets,machine.puts),(1,1))

    def initialized_driver(self):
        machine=self.machine()
        machine.u.mem_map(0x3C450000,0x10000)
        captured=[]
        def zero():
            address,value,size=[machine.reg(i) for i in range(3)]
            self.assertEqual((address,value,size),(0x3C4501D0,0,52))
            machine.u.mem_write(address,bytes(size))
            return address
        machine.hook(0x0C741A8C,zero)
        machine.hook(0x0C73DF58,lambda:captured.append(machine.reg(0)) or 0)
        machine.call(0x0C7358F5)
        self.assertEqual(captured,[0x3C4501D0])
        return machine

    def test_real_driver_initializer_matches_compiled_read_only_probe(self):
        machine=self.initialized_driver()
        self.assertEqual(machine.word(0x3C4501D4),0)
        self.assertEqual(machine.word(0x3C4501DC),0x0C7357D5)
        before=bytes(machine.u.mem_read(0x3C4501D0,52))
        self.assertEqual(machine.call(self.symbols['rh_p65_fs_driver_valid']),1)
        self.assertEqual(bytes(machine.u.mem_read(0x3C4501D0,52)),before)
        self.assertEqual(machine.gets,0)

    def test_driver_probe_rejects_each_mismatched_field(self):
        machine=self.initialized_driver()
        for offset in (0,4,12,16,20,24,28,32):
            address=0x3C4501D0+offset;original=machine.word(address)
            machine.word(address,original^1)
            self.assertEqual(machine.call(self.symbols['rh_p65_fs_driver_valid']),0)
            machine.word(address,original)

    def test_driver_probe_wrong_identity_does_not_read_driver_memory(self):
        machine=self.machine() # Driver memory intentionally unmapped.
        machine.u.mem_write(0x0C3BF9FD,b'3.100.044')
        self.assertEqual(machine.call(self.symbols['rh_p65_fs_driver_valid']),0)

    def native_fs_open(self, mode, descriptor):
        machine=self.machine();captured=[]
        source=b'resource/app/launcher/music.bin'
        machine.u.mem_write(machine.BUFFER,source+b'\0')
        def format_path():
            dst,capacity,format_pointer,source_pointer=[machine.reg(i) for i in range(4)]
            self.assertEqual((capacity,format_pointer,source_pointer),
                             (256,0x3C1BF31C,machine.BUFFER))
            machine.u.mem_write(dst,b'/'+source+b'\0')
            return len(source)+1
        def opened():
            address,flags,permissions=[machine.reg(i) for i in range(3)]
            path=bytes(machine.u.mem_read(address,len(source)+2))
            captured.append((path,flags,permissions))
            return descriptor
        machine.hook(0x0C741A50,format_path)
        machine.hook(0x0C8BEF00,opened)
        machine.hook(0x0C4F793C,lambda:machine.ERRNO)
        machine.hook(0x0C73E32C,lambda:0)
        self.symbols=dict(self.symbols,rh_p65_io_native_fs_open=0x0C7357D5)
        result=self.invoke(machine,'native_fs_open',(0x3C4501D0,machine.BUFFER,mode))
        return result,captured

    def test_native_lvgl_open_modes_and_fd_zero_encoding(self):
        for mode,flags in ((1,6),(2,1),(3,7)):
            for descriptor in (0,7):
                result,captured=self.native_fs_open(mode,descriptor)
                self.assertEqual(result,descriptor+1)
                self.assertEqual(captured,[(b'/resource/app/launcher/music.bin\0',flags,0o666)])

    def test_native_lvgl_open_failure_returns_null_not_negative_fd(self):
        result,captured=self.native_fs_open(2,-1)
        self.assertEqual(result,0)
        self.assertEqual(len(captured),1)

    def cache_drop(self, references, present=True):
        machine=self.machine();events=[]
        cache,klass,entry=0x3C408000,0x3C408100,0x3C409000
        key,userdata=machine.BUFFER,0x1234BEEF
        machine.word(cache,klass)
        machine.word(cache+24,0x20002011)
        machine.word(klass+12,0x20002001)
        machine.word(klass+20,0x20002009)
        machine.word(entry+4,references)
        machine.word(entry+8,16) # Native get_data returns entry - this offset.
        def lookup():
            events.append(('lookup',machine.reg(0),machine.reg(1),machine.reg(2)))
            return entry if present else 0
        def detach():
            events.append(('detach',machine.reg(0),machine.reg(1),machine.reg(2)))
            return 0
        def destroy():
            events.append(('destroy',machine.reg(0),machine.reg(1)))
            return 0
        machine.hook(0x20002000,lookup)
        machine.hook(0x20002008,detach)
        machine.hook(0x20002010,destroy)
        machine.hook(0x0C7416C4,lambda:0) # Downstream mutex lock.
        machine.hook(0x0C7416D4,lambda:0) # Downstream mutex unlock.
        machine.hook(0x0C73BC94,lambda:events.append(('free',machine.reg(0))) or 0)
        self.symbols=dict(self.symbols,rh_p65_io_native_cache_drop=0x0C73BAA9)
        self.invoke(machine,'native_cache_drop',(cache,key,userdata))
        return machine,events,(cache,entry,key,userdata)

    def test_native_cache_drop_forwards_third_argument_to_owner_callbacks(self):
        machine,events,(cache,entry,key,userdata)=self.cache_drop(0)
        self.assertEqual(events,[('lookup',cache,key,userdata),
            ('detach',cache,entry,userdata),('destroy',entry-16,userdata),('free',entry)])

    def test_native_cache_drop_defers_destruction_while_entry_is_referenced(self):
        machine,events,(cache,entry,key,userdata)=self.cache_drop(1)
        self.assertEqual(events,[('lookup',cache,key,userdata),('detach',cache,entry,userdata)])
        self.assertEqual(machine.u.mem_read(entry+12,1),b'\1')

    def test_native_cache_drop_missing_key_never_detaches_or_frees(self):
        machine,events,(cache,entry,key,userdata)=self.cache_drop(0,False)
        self.assertEqual(events,[('lookup',cache,key,userdata)])

    def native_path_drop(self,path='/resource/app/launcher/music.bin',identity=True,ready=True):
        machine=self.machine();events=[]
        if ready:
            machine.u.mem_map(0x3c450000,0x10000)
            machine.word(0x3c45012c,0x3c408000)
            machine.word(0x3c450130,0x3c409000)
        else:
            machine.u.mem_map(0x3c450000,0x10000)
        if not identity:machine.u.mem_write(0x0c3bf9fd,b'3.100.044')
        machine.u.mem_write(machine.BUFFER,path.encode()+b'\0')
        def capture():
            cache,key,userdata=[machine.reg(i) for i in range(3)]
            events.append((cache,bytes(machine.u.mem_read(key,24)),userdata))
            return 0
        machine.hook(0x0c73baa8,capture)
        self.symbols=dict(self.symbols,rh_p65_io_drop_path=self.symbols['rh_p65_cache_drop_path'])
        result=self.invoke(machine,'drop_path',(machine.BUFFER,))
        return result,events,machine.BUFFER

    def test_native_path_drop_constructs_both_exact_keys_and_null_userdata(self):
        result,events,path=self.native_path_drop()
        self.assertEqual(result,0)
        header=path.to_bytes(4,'little')+b'\1'+bytes(19)
        decoded=bytes(4)+path.to_bytes(4,'little')+b'\1'+bytes(15)
        self.assertEqual(events,[(0x3c409000,header,0),(0x3c408000,decoded,0)])

    def test_native_path_drop_rejects_wrong_identity(self):
        result,events,path=self.native_path_drop(identity=False)
        self.assertEqual((result,events),(-1,[]))

    def test_native_path_drop_rejects_uninitialized_caches(self):
        result,events,path=self.native_path_drop(ready=False)
        self.assertEqual((result,events),(-1,[]))

    def test_native_path_drop_rejects_non_icon_and_traversal_paths(self):
        for path in ['/data/secret.bin','/resource/app/../secret.bin',
                     '/resource/app/launcher/music.ttf','/resource/app/'+('a'*260)+'.bin']:
            result,events,_=self.native_path_drop(path=path)
            self.assertEqual((result,events),(-1,[]))

    def redirect(self, mode=2, fail_mapped=False):
        machine=self.initialized_driver();opened=[]
        state,rules=0x20007000,0x20008000
        source='/resource/app/launcher/music.bin'
        destination='/data/quickapp/files/ng.lst.corona/themes/orbit-rw6/app/launcher/music.bin'
        machine.u.mem_write(rules,source.encode().ljust(256,b'\0')+
                                 destination.encode().ljust(256,b'\0'))
        machine.u.mem_write(state,bytes(32))
        machine.word(state,rules);machine.word(state+4,1);machine.word(state+28,1)
        self.symbols=dict(self.symbols,
            rh_p65_io_prepare=self.symbols['rh_p65_fs_prepare_state'],
            rh_p65_io_redirect=self.symbols['rh_p65_fs_open'])
        driver=bytes(machine.u.mem_read(0x3C4501D0,52))
        self.assertEqual(self.invoke(machine,'prepare',(state,)),0)
        self.assertEqual(machine.word(state+24),0) # Not installed.
        self.assertEqual(bytes(machine.u.mem_read(0x3C4501D0,52)),driver)
        def string(address):
            data=bytearray()
            for i in range(256):
                value=machine.u.mem_read(address+i,1)[0]
                if not value:return bytes(data)
                data.append(value)
            raise AssertionError('Unterminated native path')
        def format_path():
            path=b'/'+string(machine.reg(3))
            self.assertLess(len(path),machine.reg(1))
            machine.u.mem_write(machine.reg(0),path+b'\0')
            return len(path)
        def native_open():
            path=string(machine.reg(0));opened.append(path)
            return -1 if fail_mapped and path==destination.encode() else 0
        machine.hook(0x0C741A50,format_path)
        machine.hook(0x0C8BEF00,native_open)
        machine.hook(0x0C4F793C,lambda:machine.ERRNO)
        machine.hook(0x0C73E32C,lambda:0)
        machine.u.mem_write(machine.BUFFER,source[1:].encode()+b'\0')
        result=self.invoke(machine,'redirect',(state,machine.BUFFER,mode))
        self.assertEqual(bytes(machine.u.mem_read(0x3C4501D0,52)),driver)
        return machine,result,opened,source.encode(),destination.encode(),state

    def test_compiled_p65_mapping_opens_theme_through_real_native_callback(self):
        machine,result,opened,source,destination,state=self.redirect()
        self.assertEqual(result,1) # fd zero encoded correctly.
        self.assertEqual(opened,[destination])
        self.assertEqual(machine.word(state+8),1)

    def test_compiled_p65_mapping_falls_back_to_stock_on_missing_theme_file(self):
        machine,result,opened,source,destination,state=self.redirect(fail_mapped=True)
        self.assertEqual(result,1)
        self.assertEqual(opened,[destination,source])
        self.assertEqual(machine.word(state+12),1)

    def test_compiled_p65_mapping_never_redirects_write_mode(self):
        machine,result,opened,source,destination,state=self.redirect(mode=1)
        self.assertEqual(result,1)
        self.assertEqual(opened,[source])
        self.assertEqual(machine.word(state+8),0)


if __name__ == '__main__': unittest.main()
