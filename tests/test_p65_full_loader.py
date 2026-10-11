"""Run exact P65 insmod -> ELF parse/layout/bind/entry -> module registry.

Allocator, file reads/fstat, locks and ROM register_driver remain modeled.
Unlike the per-relocation test, symbol resolution and binding execute the AP.
No hardware claim follows from these tests.
"""
import importlib.util
from pathlib import Path
import struct
import unittest

spec=importlib.util.spec_from_file_location('standalone_model',Path(__file__).with_name('test_p65_standalone.py'))
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)

class FullLoader(t.Machine):
    PATH='/data/quickapp/files/ng.lst.corona/rw6-component-v2.bin'
    RECORD=0x20009000
    def __init__(self,payload=None,fail_allocation=False):
        self.payload=payload if payload is not None else (t.BUILD/'rw6-corona.elf').read_bytes()
        super().__init__([],{},{self.PATH:self.payload})
        self.u.mem_map(0xe000e000,0x1000);self.word(0xe000ed88,0xf00000)
        # Keep metadata allocations clear of the largest candidate BSS block.
        self.allocations=[];self.frees=[];self.heap=0x20060000
        self.fail_allocation=fail_allocation;self.bound_symbols=self.bound_relocations=self.entries=0
        self.hook(0xc4f9f70,lambda:0);self.hook(0xc4f9f80,lambda:0)
        self.hook(0xc50b2a0,self.malloc);self.hook(0xc50b320,self.zalloc)
        self.hook(0xc50b2c8,self.aligned);self.hook(0xc50b25c,self.free)
        self.hook(0xc8be820,self.memset);self.hook(0xc5048c0,self.strncpy)
        self.hook(0xc504320,self.strncmp)
        self.hook(0xc8bd248,self.fstat);self.hook(0xc8bdba8,self.close_file)
        self.hook(0xc4f9eec,self.section_read)
        def trace(u,pc,size,user):
            if pc==0xc4fa208:self.bound_symbols+=1
            elif pc==0xc4f84c4:self.bound_relocations+=1
            elif pc==0x20010000:self.entries+=1
        self.u.hook_add(t.UC_HOOK_CODE,trace)
    def malloc(self):
        size=self.reg(0);base=self.heap;self.heap+=(size+7)&~7
        assert self.heap<0x20070000
        self.u.mem_write(base,bytes(size));return base
    def zalloc(self):
        assert self.reg(0)==160
        self.u.mem_write(self.RECORD,bytes(160));return self.RECORD
    def aligned(self):
        if self.fail_allocation:return 0
        assert self.reg(0) in (4,8)
        size=self.reg(1);base=(0x20010000,0x20050000)[len(self.allocations)]
        self.allocations.append((base,size));self.u.mem_write(base,bytes([0xa5])*size);return base
    def free(self):self.frees.append(self.reg(0));return 0
    def memset(self):
        dest,value,size=(self.reg(i) for i in range(3));self.u.mem_write(dest,bytes([value&255])*size);return dest
    def strncpy(self):
        dest,src,size=(self.reg(i) for i in range(3));data=self.string(src).encode()[:size]
        self.u.mem_write(dest,data+bytes(size-len(data)));return dest
    def strncmp(self):
        a,b,size=(self.reg(i) for i in range(3));left=self.string(a)[:size];right=self.string(b)[:size]
        return (left>right)-(left<right)
    def fstat(self):
        assert self.reg(0) in self.fds
        dest=self.reg(1);self.u.mem_write(dest,bytes(96));self.word(dest+8,0x8000)
        self.u.mem_write(dest+24,struct.pack('<Q',len(self.payload)));return 0
    def section_read(self):
        info,dest,size=(self.reg(i) for i in range(3));assert self.word(info+0x88) in self.fds
        offset=struct.unpack('<Q',self.u.mem_read(self.u.reg_read(t.UC_ARM_REG_SP),8))[0]
        if offset+size>len(self.payload):return -29
        self.u.mem_write(dest,self.payload[offset:offset+size]);return 0
    def stock_open_then_read_control(self):
        # Execute live open veneer, copied runtime open, and files_allocate.
        # Only inode/path resolution, current task and descriptor table lookup
        # are supplied by the model. The stack-to-descriptor copy is native.
        for address in (0xc8bef00,0x1c1580e4):self.u.hook_del(self.hooks[address])
        table,pointers,descriptor=0x3c42e000,0x3c42e020,0x3c42e100
        self.u.mem_write(table,b'\1');self.word(table+4,pointers);self.word(pointers,descriptor)
        self.hook(0xc4c61ac,lambda:0x3c420f00)
        self.hook(0x1c1673c8,lambda:0)
        self.hook(0x1c165da8,lambda:table)
        observed=[]
        def resolve_device(u,pc,size,user):
            temporary=self.reg(0);observed.append(temporary)
            self.u.mem_write(temporary,bytes(32));self.word(temporary,1)
            self.word(temporary+16,self.INODE);self.word(self.INODE+16,self.ops)
            # Tail-call the actual component open callback using the real
            # caller's LR; it returns into the firmware open implementation.
            u.reg_write(t.UC_ARM_REG_PC,self.word(self.ops))
        self.u.hook_add(t.UC_HOOK_CODE,resolve_device,None,0x1c157d24,0x1c157d24)
        self.u.mem_write(self.BUFFER,b'/dev/rw6-corona-v1\0')
        fd=self.invoke(0xc8bef01,(self.BUFFER,1,0o600))
        assert fd==0 and len(observed)==1 and observed[0]!=descriptor
        private=self.word(descriptor+20)
        self.fds[fd]={'path':'control','data':b'','position':0,'file':descriptor}
        read=self.invoke(0xc8beaf1,(fd,self.BUFFER,48))
        close=self.invoke(self.word(self.ops+4),(descriptor,))
        return {'fd':fd,'temporaryFile':observed[0],'descriptorFile':descriptor,
                'private':private,'read':read,'close':close}

    def load(self):
        self.u.mem_write(self.BUFFER,self.PATH.encode()+b'\0')
        self.u.mem_write(self.BUFFER+128,b'rw6_corona_v1\0')
        return self.invoke(0xc4c49ad,(self.BUFFER,self.BUFFER+128))

class FullLoaderTests(unittest.TestCase):
    def test_actual_parse_layout_bind_all_symbols_entry_and_registry(self):
        m=FullLoader();self.assertEqual(m.load(),m.RECORD)
        self.assertGreater(m.bound_relocations,250);self.assertGreater(m.bound_symbols,50)
        self.assertEqual(m.entries,1);self.assertEqual(m.word(0x3c3d67c8),m.RECORD)
        self.assertEqual(m.word(m.RECORD+0x64),0x20010001)
        self.assertEqual(m.word(m.RECORD+0x6c),0)
        self.assertEqual(m.invoke(m.word(m.RECORD+0x68),(0,)),-16)
        self.assertEqual(m.allocations[1],(0x20050000,376))
        self.assertLess(m.allocations[0][1],65536)
        self.assertEqual(m.fds,{})
        self.assertNotIn(0x20010000,m.frees);self.assertNotIn(m.RECORD,m.frees)
    def test_stage_zero_with_native_write_failure_does_not_mean_entry_was_not_called(self):
        m=FullLoader();self.assertEqual(m.load(),m.RECORD)
        self.assertEqual(m.entries,1);self.assertEqual(len(m.register_calls),1)
        self.assertEqual(m.invoke(m.word(m.ops),(m.CONTROL,)),0)
        self.assertEqual(m.invoke(m.word(m.ops+8),(m.CONTROL,m.BUFFER,48)),48)
        self.assertEqual(m.word(m.BUFFER+44),0x30005)
    def test_exact_initializer_rejection_survives_as_errno_without_marker(self):
        for kind,code in [('identity',211),('driver',212)]:
            m=FullLoader()
            if kind=='identity':m.u.mem_write(0xc3bf9fd,b'3.100.044')
            else:m.word(m.DRIVER+24,0)
            self.assertEqual(m.load(),0);self.assertEqual(m.word(m.ERRNO),code)
            self.assertEqual(m.entries,1);self.assertEqual(m.register_calls,[])
            self.assertEqual(m.word(0x3c3d67c8),0)
            self.assertIn(0x20010000,m.frees);self.assertIn(m.RECORD,m.frees)
    def test_native_open_copies_private_context_and_control_read_and_close_succeed(self):
        m=FullLoader();self.assertEqual(m.load(),m.RECORD)
        result=m.stock_open_then_read_control()
        self.assertNotEqual(result['private'],0)
        self.assertEqual((result['read'],result['close']),(48,0))

    def test_live_register_driver_body_preserves_reserve_errors_and_installs_exact_fops(self):
        for code in (0,-12):
            m=FullLoader();m.u.hook_del(m.hooks[0x1c15a954])
            m.hook(0x1c154f50,lambda:0);m.hook(0x1c154f70,lambda:0)
            inode=0x3c42d000
            def reserve():
                self.assertEqual(m.string(m.reg(0)),'/dev/rw6-corona-v1')
                self.assertEqual(m.reg(1),0o600)
                if code==0:m.word(m.reg(2),inode)
                return code
            m.hook(0x1c155888,reserve)
            self.assertEqual(m.load(),m.RECORD)
            self.assertEqual(m.invoke(m.word(m.RECORD+0x68),(0,)),-16)
            if code==0:
                self.assertEqual(struct.unpack('<H',m.u.mem_read(inode+14,2))[0]&15,1)
                ops=m.word(inode+16);self.assertNotEqual(ops,0)
                self.assertEqual(m.word(inode+24),0)
                self.assertEqual(m.invoke(m.word(ops),(m.CONTROL,)),0)
                self.assertEqual(m.invoke(m.word(ops+8),(m.CONTROL,m.BUFFER,48)),48)
                self.assertEqual(m.word(m.BUFFER+36),0)
            else:self.assertEqual(m.word(inode+16),0)

    def test_format_and_heap_failures_report_errno_before_entry(self):
        for m,code in [(FullLoader(b'not an ELF'+bytes(54)),8),(FullLoader(fail_allocation=True),12)]:
            self.assertEqual(m.load(),0);self.assertEqual(m.word(m.ERRNO),code)
            self.assertEqual(m.entries,0);self.assertEqual(m.register_calls,[])
    def test_same_resident_name_is_rejected_without_second_entry_or_allocations(self):
        m=FullLoader();self.assertEqual(m.load(),m.RECORD);n=len(m.allocations)
        self.assertEqual(m.load(),0);self.assertEqual(m.word(m.ERRNO),17)
        self.assertEqual(m.entries,1);self.assertEqual(len(m.allocations),n)

if __name__=='__main__':unittest.main()
