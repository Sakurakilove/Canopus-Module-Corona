-- Isolated P65 loader/driver probe and icon decoder preview.
-- Opening only renders this page. Native loading is a separate manual action.
local lvgl = require("lvgl")
local MODULE = "rw6_probe_v2"
local EXPECTED_SIZE = 0 -- Replaced by the builder.
local GROUPS = {} -- Replaced by the builder.
local width, height = lvgl.HOR_RES(), lvgl.VER_RES()
local root = lvgl.Object(nil, {w=width,h=height,bg_color=0x080C10,bg_opa=255,border_width=0,pad_all=0})
root:clear_flag(lvgl.FLAG.SCROLLABLE)
local title = lvgl.Label(root,{text="RW6 ICON TEST 2",x=20,y=18,text_color=0xEEE9DD})
local status = lvgl.Label(root,{text="Orbit / Fold preview\nCHECK first, then LOAD TEST.\nNative test does not replace system icons.",
    x=20,y=62,w=width-40,h=88,text_color=0xED9050})
local function show(value)status:set{text=value}end
local busy, checked, blocked = false,false,false
local style,page = "orbit",1
local images,labels = {},{}
local function brief(value)
    return tostring(value or "unknown"):gsub("[\r\n]"," "):sub(1,64)
end
local function read(path,maximum)
    if type(io)~="table" or type(io.open)~="function" then return nil,"io.open missing" end
    local opened,f,why=pcall(io.open,path,"rb")
    if not opened then return nil,"open exception: "..brief(f) end
    if not f then return nil,"open: "..brief(why) end
    local ok,data=pcall(f.read,f,maximum or "*a")
    local closed,result=pcall(f.close,f)
    if not ok then return nil,"read: "..brief(data) end
    if not closed or result==nil or result==false then return nil,"close failed" end
    if type(data)~="string" then return nil,"empty/non-string read" end
    return data
end
local function execute(command)
    if type(os)~="table" or type(os.execute)~="function" then return false,"os.execute missing" end
    local ok,a,b,c=pcall(os.execute,command)
    if not ok then return false,"execute exception: "..brief(a) end
    if a==true or a==0 then return true,"0" end
    return false,brief(c or b or a)
end
local function safe_path()
    return type(SCRIPT_PATH)=="string" and #SCRIPT_PATH>1 and #SCRIPT_PATH<180
        and SCRIPT_PATH:sub(1,1)=="/" and SCRIPT_PATH:sub(-1)=="/"
        and not SCRIPT_PATH:find("[^%w_./%-]") and not SCRIPT_PATH:find("..",1,true)
end
local function identity()
    local data,why=read("/etc/build.prop",4097)
    if data then
        if #data>4096 then return nil,"build.prop too large" end
        local props={}
        for line in (data.."\n"):gmatch("([^\n]*)\n") do
            local key,value=line:gsub("\r$",""):match("^([^=]+)=(.*)$")
            if key then
                if props[key]~=nil then return nil,"duplicate property: "..brief(key) end
                props[key]=value
            end
        end
        local version=props["ro.build.version"]
        if not version or version=="" then return nil,"build.prop version missing" end
        if props["ro.build.id"]~="3.100.043" or props["ro.product.device.devicetype"]~="watch"
            or props["ro.product.device.screenshape"]~="rect" then
            return nil,"build.prop target mismatch"
        end
        return version,"build.prop"
    end
    -- NuttX NSH is not a POSIX shell. Use its simple stdout redirection;
    -- do not assume that the previous `2>&1` syntax is supported.
    local path="/tmp/rw6-probe-v2.version"
    local ok,code=execute("getprop ro.build.version > "..path)
    if not ok then return nil,"build.prop: "..brief(why).."\ngetprop: "..brief(code) end
    local value,read_error=read(path,128)
    if not value then return nil,"getprop returned OK\nversion file: "..brief(read_error) end
    value=value:match("^%s*(.-)%s*$")
    if value=="" then return nil,"getprop version empty" end
    return value,"getprop"
end
local function check()
    checked=false
    if blocked then show("Previous test failed.\nStop here and report the screen.");return false end
    if not safe_path() then show("Unsupported SCRIPT_PATH.\nNative test was not started.");return false end
    if width~=432 or height~=514 then show("Unsupported screen size.\nRequires RW6 / 432 x 514.");return false end
    local value,source=identity()
    if not value then show("CHECK FAIL\n"..source.."\nNative test was not started.");return false end
    if value~="3.100.043" then show("Unsupported firmware:\n"..brief(value).."\nRequires RW6 / 3.100.043.");return false end
    local payload,why=read(SCRIPT_PATH.."probe.bin",EXPECTED_SIZE+1)
    if type(payload)~="string" or #payload~=EXPECTED_SIZE or payload:sub(1,7)~="\127ELF\1\1\1" then
        show("Probe resource missing/corrupt.\n"..brief(why).."\nNative test was not started.");return false
    end
    if type(os)~="table" or type(os.execute)~="function" then
        show("FW 3.100.043 / resource OK\nos.execute missing\nNative loader test is unavailable.");return false
    end
    checked=true;show("FW 3.100.043 / "..source.." OK\nProbe resource OK / execute available\nTap LOAD TEST.")
    return true
end
local function native_test()
    if busy or blocked then return end
    if not checked and not check() then return end
    busy=true;show("Native loader test in progress...")
    local log="/tmp/rw6-probe-v2.result"
    local ok,code=execute("insmod "..SCRIPT_PATH.."probe.bin "..MODULE.." > "..log)
    if not ok then
        blocked=true;busy=false
        show("LOAD FAIL / "..code.."\n"..(read(log,200) or "No shell output").."\nStop and report this screen.")
        return
    end
    local removed,exitcode=execute("rmmod "..MODULE.." > "..log)
    busy=false
    if not removed then
        blocked=true
        show("LOAD OK / EXIT FAIL "..exitcode.."\n"..(read(log,180) or "").."\nStop and report this screen.")
        return
    end
    show("PASS: load / identity / driver / exit\nIcons below test native decoding.\nReport PASS and icon appearance.")
end
local function render()
    local group=GROUPS[page]
    for i=1,4 do
        local item=group[i]
        local x=(i%2==1) and math.floor(width/2)-154 or math.floor(width/2)+26
        local y=(i<=2) and 152 or 308
        local src=SCRIPT_PATH..style.."_"..item[1]..".bin"
        if images[i] then images[i]:set{src=src} else images[i]=lvgl.Image(root,{src=src,x=x,y=y}) end
        local text=item[2]
        if labels[i] then labels[i]:set{text=text} else
            labels[i]=lvgl.Label(root,{text=text,x=x,y=y+128,w=128,text_color=0xEEE9DD})
        end
    end
end
local function button(text,x,y,w,callback)
    local box=lvgl.Object(root,{x=x,y=y,w=w,h=42,radius=14,bg_color=0x173136,border_width=0})
    box:clear_flag(lvgl.FLAG.SCROLLABLE);box:add_flag(lvgl.FLAG.CLICKABLE)
    local label=lvgl.Label(box,{text=text,text_color=0xEEE9DD,align=lvgl.ALIGN.CENTER})
    box:onevent(lvgl.EVENT.CLICKED,callback)
    return label
end
local toggle
toggle=button("FOLD",width-112,10,92,function()
    if busy then return end
    style=(style=="orbit") and "fold" or "orbit"
    toggle:set{text=(style=="orbit") and "FOLD" or "ORBIT"};render()
end)
button("CHECK",16,height-58,106,function()if not busy then check()end end)
button("LOAD TEST",132,height-58,158,native_test)
button("NEXT",300,height-58,width-316,function()if not busy then page=page%#GROUPS+1;render()end end)
render()
