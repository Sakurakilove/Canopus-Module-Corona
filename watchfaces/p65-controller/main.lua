-- AGPL-3.0: manual P65 system icon controller; opening only renders/reads status.
local lvgl=require("lvgl")
local GROUPS = {} -- Replaced by the builder.
local ASSETS = {} -- Replaced by the builder.
local EXPECTED_SIZE = 0 -- Replaced by the builder.
local EXPECTED_CRC = "" -- Replaced by the builder.
local EXPECTED_RULES = 0 -- Replaced by the builder.
local DEVICE="/dev/rw6-corona-v1"
local MODULE="rw6_corona_v1"
local COMPONENT_PATH="/data/quickapp/files/ng.lst.corona/rw6-component-v5.bin"
local INIT_PATH="/data/quickapp/files/ng.lst.corona/rw6-init-v2.status"
local STATUS_MAGIC,CONTROL_MAGIC=0x48543652,0x43365452
local width,height=lvgl.HOR_RES(),lvgl.VER_RES()
local root=lvgl.Object(nil,{w=width,h=height,bg_color=0x080C10,bg_opa=255,border_width=0,pad_all=0})
root:clear_flag(lvgl.FLAG.SCROLLABLE)
lvgl.Label(root,{text="RW6 ICON BETA 5",x=16,y=18,text_color=0xEEE9DD})
local status=lvgl.Label(root,{text="System icons / manual test\nTap INSTALL, then ORBIT or FOLD.\nSTOCK restores original icons.",x=20,y=62,w=width-40,h=88,text_color=0xED9050})
local function show(value)status:set{text=value}end
local busy,blocked=false,false
local style,page="orbit",1
local images,labels={},{}
local function brief(value)return tostring(value or "unknown"):gsub("[\r\n]"," "):sub(1,64)end
local function read(path,maximum)
    if type(io)~="table" or type(io.open)~="function" then return nil,"io.open missing" end
    local ok,f,why=pcall(io.open,path,"rb")
    if not ok or not f then return nil,"open: "..brief(why or f) end
    local got,data=pcall(f.read,f,maximum)
    local closed,result=pcall(f.close,f)
    if not got or type(data)~="string" then return nil,"read: "..brief(data) end
    if not closed or result==nil or result==false then return nil,"close failed" end
    return data
end
local function write(path,data)
    local ok,f,why=pcall(io.open,path,"wb")
    if not ok or not f then return false,"open: "..brief(why or f) end
    local at,problem=1,nil
    while at<=#data do
        local done,result=pcall(f.write,f,data:sub(at))
        if not done or result==nil or result==false then problem="write: "..brief(result);break end
        if type(result)=="number" then
            if result<1 or result>#data-at+1 then problem="invalid write count";break end
            at=at+result
        else at=#data+1 end -- Standard Lua returns the file handle on success.
    end
    local closed,result=pcall(f.close,f)
    if problem then return false,problem end
    if not closed or result==nil or result==false then return false,"close failed" end
    return true
end
local function execute(command)
    if type(os)~="table" or type(os.execute)~="function" then return false,"os.execute missing" end
    local ok,a,b,c=pcall(os.execute,command)
    if ok and (a==true or a==0) then return true end
    local raw=c or b or a
    if type(raw)=="number" and raw>=256 and raw%256==0 then
        return false,"exit "..math.floor(raw/256).." (raw "..raw..")"
    end
    return false,brief(raw)
end
local function safe_path()
    return type(SCRIPT_PATH)=="string" and #SCRIPT_PATH>1 and #SCRIPT_PATH<180
        and SCRIPT_PATH:sub(1,1)=="/" and SCRIPT_PATH:sub(-1)=="/"
        and not SCRIPT_PATH:find("[^%w_./%-]") and not SCRIPT_PATH:find("..",1,true)
end
local function identity()
    if width~=432 or height~=514 then return false,"Requires RW6 / 432 x 514" end
    if not safe_path() then return false,"Unsupported SCRIPT_PATH" end
    local data,why=read("/etc/build.prop",4097)
    if not data or #data>4096 then return false,"build.prop: "..brief(why or "too large") end
    local props={}
    for line in (data.."\n"):gmatch("([^\n]*)\n") do
        local key,value=line:gsub("\r$",""):match("^([^=]+)=(.*)$")
        if key then
            if props[key]~=nil then return false,"Duplicate build property" end
            props[key]=value
        end
    end
    if props["ro.build.version"]~="3.100.043" or props["ro.build.id"]~="3.100.043"
        or props["ro.product.device.devicetype"]~="watch" or props["ro.product.device.screenshape"]~="rect" then
        return false,"Requires RW6 / FW 3.100.043"
    end
    return true
end
local function word(data,at)
    local a,b,c,d=data:byte(at,at+3)
    -- Keep every intermediate within signed 32-bit range on compact Lua.
    if d>=128 then d=d-256 end
    return a+b*256+c*65536+d*16777216
end
local function u32(value)
    return string.char(value&255,(value>>8)&255,(value>>16)&255,(value>>24)&255)
end
local function receipt()
    local data,why=read(DEVICE,49)
    if not data then return nil,why end
    if #data~=48 then return nil,"Wrong endpoint length" end
    local values={}
    for i=1,12 do values[i]=word(data,(i-1)*4+1) end
    if values[1]~=STATUS_MAGIC or values[2]~=1 or values[11]~=EXPECTED_RULES or values[12]~=0x00030005
        or values[3]<0 or values[3]>2 or values[4]<0 or values[4]>1 then return nil,"Wrong component/schema" end
    if values[10]~=0 then return nil,"Registration failed: "..values[10] end
    return values
end
local function crc32(data)
    local crc=0xffffffff
    for i=1,#data do
        crc=crc~data:byte(i)
        for _=1,8 do crc=(crc>>1)~((crc&1)==1 and 0xedb88320 or 0) end
    end
    -- Compare wire bytes, not unsigned numbers that can exceed Lua32 integers.
    return u32(~crc)
end
local function init_status()
    local data,why=read(INIT_PATH,17)
    if not data or #data~=16 or word(data,1)~=0x324e3652 or word(data,5)~=1 then
        return "Init receipt unavailable: "..brief(why)
    end
    local stage,code=word(data,9),word(data,13)
    if stage==0 then return "No native init receipt / stage 0" end
    local label=({"Identity","Driver","Mappings","Endpoint check","Registration"})[stage] or "Unknown"
    return "Init: "..label.." / result "..code
end
local function describe(values)
    local name=({[0]="STOCK",[1]="ORBIT",[2]="FOLD"})[values[3]]
    return name.." / redirects "..values[5].."\nFallbacks "..values[6].." / result "..values[8]
end
local function stage()
    for _,dir in ipairs({"/data/quickapp","/data/quickapp/files",
        "/data/quickapp/files/ng.lst.corona","/data/quickapp/files/ng.lst.corona/themes",
        "/data/quickapp/files/ng.lst.corona/themes/rw6-orbit-v1","/data/quickapp/files/ng.lst.corona/themes/rw6-fold-v1"}) do
        execute("mkdir "..dir) -- Existing directories may return an error; verified I/O decides success.
    end
    for _,asset in ipairs(ASSETS) do
        local data,why=read(SCRIPT_PATH..asset[1],asset[3]+1)
        if not data or #data~=asset[3] then return false,"Resource "..asset[1]..": "..brief(why or "size mismatch") end
        local current=read(asset[2],asset[3]+1)
        if current~=data then
            local ok,error=write(asset[2],data)
            if not ok then return false,"Stage "..asset[1]..": "..error end
            local verified=read(asset[2],asset[3]+1)
            if verified~=data then return false,"Readback failed: "..asset[1] end
        end
    end
    return true
end
local function install()
    if busy or blocked then return end
    busy=true
    local ok,why=identity()
    if not ok then show(why.."\nInstallation was not started.");busy=false;return end
    if type(os)~="table" or type(os.execute)~="function" then show("os.execute missing\nInstallation was not started.");busy=false;return end
    -- Inspect residency BEFORE modifying any files reachable by its hook.
    local values,reason=receipt()
    if values and values[3]~=0 then
        show("READY / component already active\n"..describe(values));busy=false;return
    end
    if not values then
        local opened,node=pcall(io.open,DEVICE,"rb")
        if opened and node then
            pcall(node.close,node)
            blocked=true;show("Existing incompatible endpoint\nRestart watch before installing.");busy=false;return
        end
        local payload,error=read(SCRIPT_PATH.."component.bin",EXPECTED_SIZE+1)
        if not payload or #payload~=EXPECTED_SIZE or payload:sub(1,7)~="\127ELF\1\1\1" or crc32(payload)~=EXPECTED_CRC then
            show("Component resource invalid\n"..brief(error));busy=false;return
        end
        -- Only the three parent directories are needed by the initializer.
        for _,dir in ipairs({"/data/quickapp","/data/quickapp/files","/data/quickapp/files/ng.lst.corona"}) do execute("mkdir "..dir) end
        local copied,copy_error=write(COMPONENT_PATH,payload)
        if not copied or read(COMPONENT_PATH,EXPECTED_SIZE+1)~=payload then
            show("MODULE COPY FAIL\n"..brief(copy_error or "readback mismatch"));busy=false;return
        end
        local marker=u32(0x324e3652)..u32(1)..u32(0)..u32(0)
        local prepared,prepare_error=write(INIT_PATH,marker)
        if not prepared or read(INIT_PATH,17)~=marker then show("INIT RECEIPT FAIL\n"..brief(prepare_error or "readback mismatch"));busy=false;return end
        -- Drop module/readback allocations before modlib requests executable RAM.
        payload=nil
        if type(collectgarbage)=="function" then pcall(collectgarbage,"collect") end
        show("Loading component...")
        -- This NSH redirects stdout only; its insmod errors go to stderr.
        -- Do not claim that an empty redirected file contains a loader errno.
        local loaded,code=execute("insmod "..COMPONENT_PATH.." "..MODULE)
        values,reason=receipt()
        if not loaded or not values then
            blocked=true;busy=false
            show("INSTALL FAIL / "..brief(code or reason).."\n"..init_status().."\nStop and report this screen.");return
        end
    end
    show("Staging icon resources...")
    local staged,reason=stage()
    busy=false
    if not staged then show("STAGE FAIL\n"..reason.."\nTap INSTALL to retry.");return end
    show("READY / "..#ASSETS.." resources staged\nTap ORBIT or FOLD.\nSTOCK restores original icons.")
end
local function apply(mode)
    if busy then return end
    busy=true
    local ok,why=identity()
    if not ok then show(why);busy=false;return end
    local previous,error=receipt()
    if not previous then show("Component unavailable\n"..brief(error).."\nTap INSTALL first.");busy=false;return end
    local sequence=1
    if previous[7]>=0 and previous[7]<0x7fffffff then sequence=previous[7]+1 end
    local sent,reason=write(DEVICE,u32(CONTROL_MAGIC)..u32(sequence)..u32(mode)..u32(0))
    local values,read_error=receipt()
    busy=false
    if not values then show("RECEIPT FAIL\n"..brief(read_error));return end
    if values[7]~=sequence or values[8]~=0 or values[3]~=mode or not sent then
        show("APPLY FAIL / "..values[8].."\n"..brief(reason or "request/mode mismatch").."\n"..describe(values));return
    end
    show("APPLIED / "..describe(values).."\nOpen system app list to check icons.")
end
local function render()
    for i,item in ipairs(GROUPS[page]) do
        local x=(i%2==1) and math.floor(width/2)-154 or math.floor(width/2)+26
        local y=(i<=2) and 152 or 308
        local src=SCRIPT_PATH..style.."_"..item[1]..".bin"
        if images[i] then images[i]:set{src=src} else images[i]=lvgl.Image(root,{src=src,x=x,y=y}) end
        if labels[i] then labels[i]:set{text=item[2]} else labels[i]=lvgl.Label(root,{text=item[2],x=x,y=y+128,w=128,text_color=0xEEE9DD}) end
    end
end
local function button(text,x,y,w,callback)
    local box=lvgl.Object(root,{x=x,y=y,w=w,h=42,radius=14,bg_color=0x173136,border_width=0})
    box:clear_flag(lvgl.FLAG.SCROLLABLE);box:add_flag(lvgl.FLAG.CLICKABLE)
    local label=lvgl.Label(box,{text=text,text_color=0xEEE9DD,align=lvgl.ALIGN.CENTER})
    box:onevent(lvgl.EVENT.CLICKED,callback)
    return label
end
button("NEXT",222,10,86,function()if not busy then page=page%#GROUPS+1;render()end end)
local toggle
toggle=button("FOLD",320,10,92,function()
    if busy then return end
    style=(style=="orbit") and "fold" or "orbit"
    toggle:set{text=(style=="orbit") and "FOLD" or "ORBIT"};render()
end)
button("INSTALL",8,height-58,100,install)
button("ORBIT",114,height-58,100,function()apply(1)end)
button("FOLD",220,height-58,100,function()apply(2)end)
button("STOCK",326,height-58,98,function()apply(0)end)
render()
local current=receipt()
if current then show("Component ready / "..describe(current).."\nOpen system app list after applying.") end
