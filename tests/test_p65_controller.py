"""Lua 5.4 protocol/staging failure tests; no hardware access."""
from pathlib import Path
import unittest
import zlib
import struct
import json
import os
import subprocess
import tempfile
from lupa.lua54 import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
BOOTSTRAP=r'''
MODE=...
SCRIPT_PATH="/data/watchface/979810116504/lua/"
local device="/dev/rw6-corona-v1"
local component="/data/quickapp/files/ng.lst.corona/rw6-component-v5.bin"
local marker="/data/quickapp/files/ng.lst.corona/rw6-init-v2.status"
files,commands,buttons,images,mutations={},{},{},{},{}
files[SCRIPT_PATH.."component.bin"]="\127ELF\1\1\1"..string.rep("\0",57)
files[SCRIPT_PATH.."orbit_native_music.bin"]="ORBIT"
files[SCRIPT_PATH.."fold_native_music.bin"]="FOLDS"
files["/etc/build.prop"]="ro.build.version=3.100.043\nro.build.id=3.100.043\nro.product.device.devicetype=watch\nro.product.device.screenshape=rect\n"
if MODE=="version"then files["/etc/build.prop"]=files["/etc/build.prop"]:gsub("3.100.043","3.100.044")end
if MODE=="duplicate"then files["/etc/build.prop"]=files["/etc/build.prop"].."ro.build.version=3.100.043\n"end
if MODE=="corrupt_component"then files[SCRIPT_PATH.."component.bin"]="bad"end
if MODE=="component_crc"then files[SCRIPT_PATH.."component.bin"]=files[SCRIPT_PATH.."component.bin"]:sub(1,63).."X"end
if MODE=="corrupt_asset"then files[SCRIPT_PATH.."orbit_native_music.bin"]="bad"end
if MODE=="missing_props"then files["/etc/build.prop"]=nil end
state={mode=0,seq=0,result=0,reg=0,redirects=0}
local function snapshot()
    return string.pack("<I4I4I4I4I4I4I4i4I4i4I4I4",0x48543652,1,state.mode,state.mode==0 and 0 or 1,state.redirects,0,state.seq,state.result,1,state.reg,108,0x30005)
end
if MODE=="existing"then files[device]="native";state.mode=1;state.seq=8;state.redirects=12 end
if MODE=="foreign"then files[device]="foreign"end
local function widget(p)
    local o={props=p or {}}
    function o:set(v)for k,x in pairs(v)do self.props[k]=x end end
    function o:clear_flag()end
    function o:add_flag()end
    function o:onevent(e,cb)self.callback=cb end
    return o
end
local lvgl={FLAG={SCROLLABLE=1,CLICKABLE=2},EVENT={CLICKED=1},ALIGN={CENTER=0}}
function lvgl.HOR_RES()return 432 end
function lvgl.VER_RES()return 514 end
function lvgl.Object(parent,p)local o=widget(p);buttons[#buttons+1]=o;return o end
function lvgl.Label(parent,p)local o=widget(p);if p.y==62 then status=o end;return o end
function lvgl.Image(parent,p)local o=widget(p);images[#images+1]=o;return o end
package.preload.lvgl=function()return lvgl end
io.open=function(path,mode)
    if mode=="rb"then
        local data=files[path]
        if not data then return nil,"not found"end
        if path==device and data=="native"then data=snapshot()end
        return {read=function(self,n)return data:sub(1,n)end,close=function()return true end}
    end
    if mode~="wb"then error("unexpected mode")end
    if path==device and not files[path]then return nil,"missing endpoint"end
    if MODE=="write_open_failure"and path~=device then return nil,"no space"end
    if MODE=="module_copy_failure"and path==component then return nil,"no space"end
    if MODE=="marker_write_failure"and path==marker then return nil,"no space"end
    if MODE=="log_write_failure"and path=="/tmp/rw6-corona-v3.result"then return nil,"no space"end
    local data=""
    return {write=function(self,v)
        if MODE=="write_failure"then return nil end
        if MODE=="partial_write"then local n=math.min(2,#v);data=data..v:sub(1,n);return n end
        data=data..v;return self
    end,close=function()
        if path==device then
            if #data~=16 then error("bad packet")end
            local magic,seq,mode,flags=string.unpack("<I4I4I4I4",data)
            if magic~=0x43365452 or flags~=0 then error("bad control")end
            mutations[#mutations+1]=mode
            if MODE~="stale_receipt"then state.seq=seq end
            if MODE=="native_reject"then state.result=-74;return nil end
            state.mode=mode;state.result=0
        else
            local corrupt=MODE=="readback_failure" or MODE=="module_readback_failure"and path==component
                or MODE=="marker_readback_failure"and path==marker
            files[path]=corrupt and "bad"or data
        end
        if MODE=="close_failure"and path~=device then return nil end
        return true
    end}
end
os.execute=function(cmd)
    commands[#commands+1]=cmd
    if cmd:find("2>&1",1,true)or cmd:match("rmmod")then error("unsafe command")end
    if cmd:match("^mkdir ")then return nil,"exit",17 end -- Existing dirs are fine.
    if not cmd:match("^insmod /data/quickapp/files/ng.lst.corona/rw6%-component%-v5.bin rw6_corona_v1$")then error("unknown command")end
    if files[component]~=files[SCRIPT_PATH.."component.bin"]then error("unverified staged module")end
    if #files[marker]~=16 then error("missing init marker")end
    if MODE=="load_failure"then return nil,"exit",1 end
    if MODE=="raw_load_failure"then return 65280 end
    if MODE=="loader_memory"then files["/tmp/rw6-corona-v3.result"]="nsh: insmod: insmod failed: 12\n";return 65280 end
    if MODE=="loader_identity"then files["/tmp/rw6-corona-v3.result"]="nsh: insmod: insmod failed: 211\n";return 65280 end
    if MODE=="driver_reject"then files[marker]=string.pack("<IIIi",0x324e3652,1,2,-212);return 65280 end
    if MODE~="no_endpoint"then files[device]="native" end
    if MODE=="registration_failure"then state.reg=-5 end
    files[marker]=string.pack("<IIIi",0x324e3652,1,5,state.reg)
    if MODE=="numeric_success"then return 0 end
    return true,"exit",0
end
if MODE=="missing_execute"then os.execute=nil end
'''

class ControllerTests(unittest.TestCase):
    def page(self,mode='success',path=None):
        lua=LuaRuntime(unpack_returned_tuples=True);lua.execute(BOOTSTRAP,mode)
        if path is not None:lua.globals().SCRIPT_PATH=path
        lua.execute(self.patched_source());return lua
    def patched_source(self):
        source=(ROOT/'watchfaces/p65-controller/main.lua').read_text()
        source=source.replace('local EXPECTED_RULES = 0 -- Replaced by the builder.','local EXPECTED_RULES = 108')
        source=source.replace('local EXPECTED_SIZE = 0 -- Replaced by the builder.','local EXPECTED_SIZE = 64')
        crc=zlib.crc32(b'\x7fELF\x01\x01\x01'+bytes(57))
        literal='"'+''.join('\\%03d'%b for b in struct.pack('<I',crc))+'"'
        source=source.replace('local EXPECTED_CRC = "" -- Replaced by the builder.','local EXPECTED_CRC = '+literal)
        source=source.replace('local GROUPS = {} -- Replaced by the builder.','local GROUPS = {{{"music","Music"},{"weather","Weather"},{"heartrate","Heart"},{"settings","Settings"}}}')
        source=source.replace('local ASSETS = {} -- Replaced by the builder.','local ASSETS = {{"orbit_native_music.bin","/data/quickapp/files/ng.lst.corona/themes/rw6-orbit-v1/music.bin",5},{"fold_native_music.bin","/data/quickapp/files/ng.lst.corona/themes/rw6-fold-v1/music.bin",5}}')
        return source
    def press(self,lua,index):lua.globals().buttons[index].callback()
    def text(self,lua):return lua.globals().status.props.text
    def test_open_only_renders_and_reads_existing_status_without_shell_or_writes(self):
        for mode in ('success','existing'):
            l=self.page(mode);self.assertEqual(len(l.globals().commands),0);self.assertEqual(len(l.globals().mutations),0)
            self.assertEqual(len(l.globals().images),4)
        self.assertIn('redirects 12',self.text(l))
    def test_install_verifies_staging_and_endpoint_without_applying_then_three_modes(self):
        l=self.page();self.press(l,4)
        self.assertIn('READY',self.text(l));self.assertEqual(len(l.globals().mutations),0)
        self.assertEqual(len(l.globals().commands),10)
        for index,mode in ((5,1),(6,2),(7,0)):
            self.press(l,index);self.assertIn('APPLIED',self.text(l));self.assertEqual(l.globals().state.mode,mode)
        self.assertEqual(l.globals().state.seq,3)
    def test_numeric_shell_success_and_partial_writes_are_supported(self):
        for mode in ('numeric_success','partial_write'):
            l=self.page(mode);self.press(l,4);self.press(l,5);self.assertIn('APPLIED',self.text(l))
    def test_identity_path_or_component_errors_never_mutate_or_run_shell(self):
        for mode in ('version','duplicate','missing_props','corrupt_component','component_crc','missing_execute'):
            l=self.page(mode);self.press(l,4);self.assertEqual(len(l.globals().commands),0)
            self.assertEqual(len(l.globals().mutations),0)
        for path in ('relative/','/tmp/../evil/','/tmp/a b/',"/tmp/a';reboot;'/"):
            l=self.page(path=path);self.press(l,4);self.assertEqual(len(l.globals().commands),0)
    def test_asset_staging_failure_keeps_loaded_component_for_retry(self):
        l=self.page('corrupt_asset');self.press(l,4);self.assertIn('STAGE FAIL',self.text(l))
        self.assertEqual(l.globals().files['/dev/rw6-corona-v1'],'native')
        l.execute('MODE="success"; files[SCRIPT_PATH.."orbit_native_music.bin"]="ORBIT"')
        self.press(l,4);self.assertIn('READY',self.text(l))
        self.assertEqual(sum('insmod' in l.globals().commands[i] for i in range(1,len(l.globals().commands)+1)),1)
    def test_shell_success_without_valid_endpoint_never_ready_and_blocks_retry(self):
        for mode in ('no_endpoint','load_failure','raw_load_failure','driver_reject','registration_failure'):
            l=self.page(mode);self.press(l,4);self.assertIn('INSTALL FAIL',self.text(l))
            n=len(l.globals().commands);self.press(l,4);self.assertEqual(len(l.globals().commands),n)
    def test_module_copy_and_init_marker_failures_never_run_insmod(self):
        for mode,message in [('module_copy_failure','MODULE COPY FAIL'),('module_readback_failure','MODULE COPY FAIL'),
            ('marker_write_failure','INIT RECEIPT FAIL'),('marker_readback_failure','INIT RECEIPT FAIL')]:
            l=self.page(mode);self.press(l,4);self.assertIn(message,self.text(l))
            self.assertEqual(len(l.globals().commands),3)
    def test_raw_shell_status_and_native_init_stage_are_reported_separately(self):
        l=self.page('raw_load_failure');self.press(l,4)
        self.assertIn('exit 255 (raw 65280)',self.text(l));self.assertIn('stage 0',self.text(l))
        l=self.page('driver_reject');self.press(l,4)
        self.assertIn('Driver / result -212',self.text(l))
        l=self.page('registration_failure');self.press(l,4)
        self.assertIn('Registration / result -5',self.text(l))
    def test_existing_valid_component_is_reused_and_foreign_endpoint_never_loaded_over(self):
        for mode in ('existing','foreign'):
            l=self.page(mode);self.press(l,4)
            self.assertEqual(len(l.globals().commands),0)
        self.assertIn('incompatible endpoint',self.text(l))
    def test_apply_requires_endpoint_and_matching_success_receipt(self):
        l=self.page();self.press(l,5);self.assertEqual(len(l.globals().mutations),0)
        for mode in ('native_reject','stale_receipt'):
            l=self.page(mode);self.press(l,4);self.press(l,5);self.assertIn('APPLY FAIL',self.text(l))
        self.assertNotIn('APPLIED',self.text(l))
    def test_stock_remains_available_even_after_install_is_blocked(self):
        l=self.page('no_endpoint');self.press(l,4);self.assertIn('INSTALL FAIL',self.text(l))
        l.execute('MODE="success"; files["/dev/rw6-corona-v1"]="native"; state.mode=1')
        self.press(l,7);self.assertIn('APPLIED',self.text(l));self.assertEqual(l.globals().state.mode,0)
    def test_preview_navigation_never_writes_or_loads(self):
        l=self.page();self.press(l,3);self.press(l,2)
        self.assertIn('/fold_music.bin',l.globals().images[1].props.src)
        self.assertEqual(len(l.globals().commands),0);self.assertEqual(len(l.globals().mutations),0)
    def test_maximum_signed_sequence_wraps_to_one_without_reusing_previous_receipt(self):
        l=self.page('existing');l.execute('state.seq=0x7fffffff');self.press(l,7)
        self.assertIn('APPLIED',self.text(l));self.assertEqual(l.globals().state.seq,1)
    @unittest.skipUnless(os.environ.get('RW6_LUA32_BINARY'),'Set RW6_LUA32_BINARY to Lua 5.4 LUA_32BITS build')
    def test_lua32_crc_wire_protocol_install_stages_errors_and_sequence_wrap(self):
        executable=os.environ['RW6_LUA32_BINARY']
        cases=[('success','READY'),('partial_write','READY'),('numeric_success','READY'),
            ('component_crc','Component resource invalid'),('module_copy_failure','MODULE COPY FAIL'),
            ('module_readback_failure','MODULE COPY FAIL'),('marker_write_failure','INIT RECEIPT FAIL'),
            ('marker_readback_failure','INIT RECEIPT FAIL'),('raw_load_failure','exit 255 (raw 65280)'),
            ('driver_reject','Driver / result -212'),('registration_failure','Registration / result -5'),
            ('loader_memory','exit 255'),('loader_identity','exit 255')]
        with tempfile.TemporaryDirectory() as temp:
            for mode,message in cases:
                script='assert(math.maxinteger==2147483647 and string.packsize("j")==4)\n'
                script+='assert(load('+json.dumps(BOOTSTRAP)+'))('+json.dumps(mode)+')\n'
                script+='assert(load('+json.dumps(self.patched_source())+'))()\n'
                script+='assert(#commands==0 and #mutations==0);buttons[4].callback()\n'
                script+='assert(status.props.text:find('+json.dumps(message)+',1,true),status.props.text)\n'
                if message=='READY':
                    script+='for _,i in ipairs({5,6,7})do buttons[i].callback();assert(status.props.text:find("APPLIED",1,true),status.props.text)end;assert(state.seq==3)\n'
                    script+='state.seq=0x7fffffff;buttons[7].callback();assert(state.seq==1 and status.props.text:find("APPLIED",1,true))\n'
                else:script+='assert(#mutations==0)\n'
                path=Path(temp)/'check.lua';path.write_text(script)
                result=subprocess.run([executable,str(path)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,msg=mode+': '+result.stderr)

if __name__=='__main__':unittest.main()
