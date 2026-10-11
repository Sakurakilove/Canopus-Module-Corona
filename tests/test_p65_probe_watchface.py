"""Lua 5.4 smoke tests; LVGL, shell and files are mocked, never device access."""
from pathlib import Path
import unittest
from lupa.lua54 import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
BOOTSTRAP=r'''
SCRIPT_PATH="/data/watchface/979810116502/lua/"
MODE=...
files,commands,buttons,widgets,images={},{},{},{},{}
local payload="\127ELF\1\1\1"..string.rep("\0",57)
files[SCRIPT_PATH.."probe.bin"]=(MODE=="corrupt") and "bad" or payload
local props="ro.build.version=3.100.043\nro.build.id=3.100.043\nro.product.device.devicetype=watch\nro.product.device.screenshape=rect\n"
if MODE:match("^prop") or MODE=="missing_execute" then files["/etc/build.prop"]=props end
if MODE=="prop_version"then files["/etc/build.prop"]=props:gsub("ro.build.version=3.100.043","ro.build.version=3.100.044")end
if MODE=="prop_build"then files["/etc/build.prop"]=props:gsub("ro.build.id=3.100.043","ro.build.id=wrong")end
if MODE=="prop_duplicate"then files["/etc/build.prop"]=props.."ro.build.version=3.100.043\n"end
if MODE=="prop_large"then files["/etc/build.prop"]=props..string.rep("x",4096)end
if MODE=="prop_missing"then files["/etc/build.prop"]="ro.build.id=3.100.043\n"end
if MODE=="prop_crlf"then files["/etc/build.prop"]=props:gsub("\n","\r\n")end
local function widget(props)
    local obj={props=props or {}}
    function obj:set(p)for k,v in pairs(p)do self.props[k]=v end end
    function obj:clear_flag(_)end
    function obj:add_flag(_)end
    function obj:onevent(_,cb)self.callback=cb end
    widgets[#widgets+1]=obj
    return obj
end
local lvgl={FLAG={SCROLLABLE=1,CLICKABLE=2},EVENT={CLICKED=7},ALIGN={CENTER=0}}
function lvgl.HOR_RES()return 432 end
function lvgl.VER_RES()return 514 end
function lvgl.Object(parent,p)local w=widget(p);buttons[#buttons+1]=w;return w end
function lvgl.Label(parent,p)local w=widget(p);if p.x==20 and p.y==62 then status=w end;return w end
function lvgl.Image(parent,p)local w=widget(p);images[#images+1]=w;return w end
package.preload.lvgl=function()return lvgl end
io.open=function(path,mode)
    if MODE=="open_exception"then error("permission exception")end
    if not files[path]then return nil,"no such file" end
    return {read=function(self,size)
        local v=files[path]
        return type(size)=="number" and v:sub(1,size) or v
    end,close=function()if MODE=="close_failure"then return nil end;return true end}
end
os.execute=function(command)
    commands[#commands+1]=command
    -- Model the small NSH dialect rather than silently accepting POSIX syntax.
    if command:find("2>&1",1,true)then return nil,"exit",2 end
    if command:match("^getprop ")then
        if MODE=="getprop"then return nil,"exit",1 end
        if MODE~="unreadable_result"then
            files["/tmp/rw6-probe-v2.version"]=(MODE=="version") and "3.100.044\n" or "3.100.043\n"
        end
    elseif command:match("^insmod ")then
        if MODE=="load"then files["/tmp/rw6-probe-v2.result"]="insmod failed";return nil,"exit",1 end
    elseif command:match("^rmmod ")then
        if MODE=="exit"then files["/tmp/rw6-probe-v2.result"]="rmmod failed";return nil,"exit",1 end
    else error("unexpected shell command")end
    if MODE=="numeric_success"then return 0 end
    return true,"exit",0
end
if MODE=="missing_execute"then os.execute=nil end
'''


class ProbeLuaTests(unittest.TestCase):
    def page(self,mode='success',path=None):
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute(BOOTSTRAP,mode)
        if path is not None:lua.globals().SCRIPT_PATH=path
        source=(ROOT/'watchfaces/p65-probe/main.lua').read_text()
        source=source.replace('local EXPECTED_SIZE = 0 -- Replaced by the builder.','local EXPECTED_SIZE = 64')
        source=source.replace('local GROUPS = {} -- Replaced by the builder.',
            'local GROUPS = {{{"music","Music"},{"weather","Weather"},{"heartrate","Heart"},{"settings","Settings"}}}')
        lua.execute(source)
        return lua

    def press(self,lua,index):
        # root, style toggle, CHECK, LOAD TEST, NEXT
        lua.globals().buttons[index].callback()

    def test_open_only_renders_four_icons_and_never_runs_shell(self):
        l=self.page();self.assertEqual(len(l.globals().commands),0)
        self.assertEqual(len(l.globals().images),4)

    def test_success_checks_then_loads_and_removes_exact_probe(self):
        l=self.page();self.press(l,3);self.press(l,4)
        commands=[l.globals().commands[i] for i in range(1,4)]
        self.assertTrue(commands[0].startswith('getprop ro.build.version'))
        self.assertIn("/probe.bin rw6_probe_v2 > ",commands[1])
        self.assertTrue(commands[2].startswith("rmmod rw6_probe_v2 > "))
        self.assertTrue(all('2>&1' not in c for c in commands))
        self.assertIn('PASS:',l.globals().status.props.text)

    def test_readable_build_prop_needs_no_getprop_or_temporary_version_file(self):
        for mode in ('prop_valid','prop_crlf'):
            l=self.page(mode);self.press(l,3)
            self.assertEqual(len(l.globals().commands),0)
            self.assertIn('build.prop OK',l.globals().status.props.text)
            self.press(l,4)
            self.assertEqual(len(l.globals().commands),2)
            self.assertIn('PASS:',l.globals().status.props.text)

    def test_invalid_readable_build_prop_is_never_bypassed_with_shell(self):
        for mode in ('prop_version','prop_build','prop_duplicate','prop_large','prop_missing'):
            l=self.page(mode);self.press(l,4)
            self.assertEqual(len(l.globals().commands),0)
            self.assertNotIn('PASS:',l.globals().status.props.text)

    def test_missing_execute_reports_the_interface_and_never_tries_native_load(self):
        l=self.page('missing_execute');self.press(l,4)
        self.assertEqual(len(l.globals().commands),0)
        self.assertIn('os.execute missing',l.globals().status.props.text)
        self.assertIn('FW 3.100.043',l.globals().status.props.text)

    def test_read_failure_close_failure_and_open_exception_are_visible(self):
        for mode,message in [('unreadable_result','version file: open:'),
                ('close_failure','version file: close failed'),('open_exception','open exception:')]:
            l=self.page(mode);self.press(l,4)
            self.assertEqual(len(l.globals().commands),1)
            self.assertIn(message,l.globals().status.props.text)
            self.assertNotIn('PASS:',l.globals().status.props.text)

    def test_nonzero_shell_status_is_shown_without_masking_it(self):
        l=self.page('getprop');self.press(l,4)
        self.assertIn('getprop: 1',l.globals().status.props.text)
        self.assertEqual(len(l.globals().commands),1)

    def test_firmware_numeric_zero_execute_success_is_supported(self):
        l=self.page('numeric_success');self.press(l,4)
        self.assertIn('PASS:',l.globals().status.props.text)

    def test_load_button_performs_check_if_needed(self):
        l=self.page();self.press(l,4)
        self.assertEqual(len(l.globals().commands),3)
        self.assertIn('PASS:',l.globals().status.props.text)

    def test_wrong_version_bad_resource_or_getprop_failure_never_loads(self):
        for mode in ('version','corrupt','getprop'):
            l=self.page(mode);self.press(l,4)
            self.assertEqual(len(l.globals().commands),1)
            self.assertNotIn('PASS:',l.globals().status.props.text)

    def test_bad_script_path_never_runs_shell(self):
        for path in ("relative/", "/tmp/../evil/", "/tmp/a';reboot;'/", "/tmp/a b/"):
            l=self.page(path=path);self.press(l,4)
            self.assertEqual(len(l.globals().commands),0)

    def test_load_failure_blocks_retry_and_never_unloads_other_module(self):
        l=self.page('load');self.press(l,4)
        self.assertEqual(len(l.globals().commands),2)
        self.press(l,3);self.press(l,4)
        self.assertEqual(len(l.globals().commands),2)

    def test_exit_failure_blocks_retry(self):
        l=self.page('exit');self.press(l,4)
        self.assertIn('EXIT FAIL',l.globals().status.props.text)
        self.press(l,4);self.assertEqual(len(l.globals().commands),3)

    def test_style_switch_reuses_widgets_and_changes_sources(self):
        l=self.page();self.press(l,2)
        self.assertEqual(len(l.globals().images),4)
        self.assertIn('/fold_music.bin',l.globals().images[1].props.src)
        self.press(l,2);self.assertIn('/orbit_music.bin',l.globals().images[1].props.src)
        self.assertEqual(len(l.globals().commands),0)


if __name__=='__main__':unittest.main()
