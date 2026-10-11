/* P65-only standalone Corona icon component. No old Supervisor/Manager,
 * app registration, autoload, registry, arbitrary mappings or heap ownership.
 * Once a driver registration is attempted, retain all callback code until
 * power-off; never allow the loader to free firmware-reachable callbacks. */
#include "resource_hook.h"
#include "resource_hook_internal.h"
#include "resource_hook_p65_fs.h"
#include "resource_hook_p65_io.h"
#include "resource_hook_p65_cache.h"
#include "resource_hook_p65_standalone.h"
#include "canopus_p65_abi.h"
#include <stddef.h>
#include "p65_theme_assets.h"

_Static_assert(sizeof(struct rh_p65_unload_pair)==8,"stock P65 unload pair");
_Static_assert(sizeof(file_operations)==48,"exact P65 fops layout");
struct client {
    uint32_t allocated;
    uint32_t used, cursor, ready, overflow;
    uint8_t command[RH_P65_CONTROL_BYTES];
    uint32_t status[RH_P65_STATUS_WORDS];
};
static struct client clients[4];
static uint32_t mode,hooked,redirected,fallback,sequence,epoch,writer,revision;
static int32_t result,registration_result;
/* Lua creates/reset this exact 16-byte marker before manual insmod. No
 * startup work and no shell stderr dependency. Failure to report is optional. */
static void init_receipt(uint32_t stage,int32_t code){
    uint32_t words[4]={0x324e3652u,1u,stage,(uint32_t)code};
    int fd=rh_p65_io_open("/data/quickapp/files/ng.lst.corona/rw6-init-v2.status",2);
    uint32_t used=0;int wrote;
    if(fd<0)return;
    while(used<sizeof(words)){
        wrote=rh_p65_io_write(fd,((const uint8_t *)words)+used,sizeof(words)-used);
        if(wrote<=0||(uint32_t)wrote>sizeof(words)-used)break;
        used+=(uint32_t)wrote;
    }
    rh_p65_io_close(fd);
}
static int snapshot_valid(unsigned which){
    const struct rh_snapshot *snap=rh_p65_theme_snapshots[which];
    struct rh_mapping_view view=rh_snapshot_view(snap);
    const char *pool=rh_snapshot_pool(snap);unsigned i,j;
    static const char root[]=RH_APP_FILES_ROOT;
    const unsigned base=sizeof(root)-1u;
    if(rh_validate_view(&view)||snap->count!=RH_P65_THEME_RULES)return -1;
    for(i=0;i<snap->count;i++){
        const struct rh_indexed_rule *r=&snap->rules[i];
        const char *dst=rh_p65_theme_assets[which][i].path;
        if(r->flags||r->reserved||!r->source_length||!r->destination_length||
           (uint32_t)r->source_offset+r->source_length>=snap->pool_bytes||
           (uint32_t)r->destination_offset+r->destination_length>=snap->pool_bytes||
           pool[r->source_offset+r->source_length]||pool[r->destination_offset+r->destination_length])return -1;
        if(i&&rh_key_compare(pool+snap->rules[i-1].source_offset,snap->rules[i-1].source_length,
            pool+r->source_offset,r->source_length)>=0)return -1;
        /* The file validated by CRC must be exactly the file selected by
         * the compact resolver, including its fixed quickapp root. */
        if(base+r->destination_length>=RH_PATH)return -1;
        for(j=0;j<base;j++)if(dst[j]!=root[j])return -1;
        for(j=0;j<=r->destination_length;j++)
            if(dst[base+j]!=pool[r->destination_offset+j])return -1;
        if(!rh_mapping_valid(pool+r->source_offset,dst))return -1;
    }
    return 0;
}
static uint32_t load(const uint32_t *p){return __atomic_load_n(p,__ATOMIC_ACQUIRE);}
static void store(uint32_t *p,uint32_t value){__atomic_store_n(p,value,__ATOMIC_RELEASE);}
static int claim(uint32_t *p,uint32_t expected,uint32_t value){
    return __atomic_compare_exchange_n(p,&expected,value,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
}
static uint32_t word(const uint8_t *p){
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
/* Exact P65 struct file: flags +0, refs +4, pos +8, inode +16,
 * f_priv +20. open() first invokes fops->open on a STACK struct file, then
 * files_allocate copies f_priv into the descriptor table. The file address
 * therefore cannot identify an open session. See P65_STANDALONE_BETA.md. */
static uintptr_t *file_private(void *file){
    return (uintptr_t *)((uint8_t *)file+20u);
}
static struct client *client(void *file){
    uintptr_t value;unsigned i;
    if(!file)return NULL;
    value=*file_private(file);
    for(i=0;i<4;i++)if(value==(uintptr_t)&clients[i]&&load(&clients[i].allocated))
        return &clients[i];
    return NULL;
}
static int control_open(void *file){
    unsigned i;if(!file)return -22;
    if(client(file))return -16;
    *file_private(file)=0;
    for(i=0;i<4;i++){
        if(claim(&clients[i].allocated,0,1)){
            clients[i].used=clients[i].cursor=clients[i].ready=clients[i].overflow=0;
            *file_private(file)=(uintptr_t)&clients[i];
            return 0;
        }
    }
    return -24;
}
static int hook_open(void *driver,const char *path,int access){
    uint32_t selected=load(&mode);int value;
    rh_open_fn original=(rh_open_fn)(uintptr_t)RH_P65_FS_OPEN;
    if(!selected||selected>2)return original(driver,path,access);
    {
        struct rh_state state={0};
        struct rh_mapping_view view=rh_snapshot_view(rh_p65_theme_snapshots[selected-1u]);
        state.original=original;
        state.driver=(void *)(uintptr_t)RH_P65_FS_DRIVER;
        value=rh_posix_open_view(&state,&view,driver,path,access);
        if(state.redirected)__atomic_fetch_add(&redirected,state.redirected,__ATOMIC_RELAXED);
        if(state.fallback)__atomic_fetch_add(&fallback,state.fallback,__ATOMIC_RELAXED);
    }
    return value;
}
static int driver_owned(void){
    const volatile uint32_t *d=(const volatile uint32_t *)(uintptr_t)RH_P65_FS_DRIVER;
    uintptr_t open=d[3];
    return (d[0]&255u)=='/'&&d[1]==0&&
        (open==RH_P65_FS_OPEN||(load(&hooked)&&open==(uintptr_t)hook_open))&&
        d[4]==RH_P65_FS_CLOSE&&d[5]==RH_P65_FS_READ&&d[6]==RH_P65_FS_WRITE&&
        d[7]==RH_P65_FS_SEEK&&d[8]==RH_P65_FS_TELL;
}
static int verify_asset(const struct rh_p65_asset *asset){
    /* Two nibble lookups per byte replace eight polynomial iterations. */
    static const uint32_t crc_nibble[16]={
        0x00000000u,0x1db71064u,0x3b6e20c8u,0x26d930acu,
        0x76dc4190u,0x6b6b51f4u,0x4db26158u,0x5005713cu,
        0xedb88320u,0xf00f9344u,0xd6d6a3e8u,0xcb61b38cu,
        0x9b64c2b0u,0x86d3d2d4u,0xa00ae278u,0xbdbdf21cu};
    uint8_t bytes[512],extra;uint32_t used=0,crc=0xffffffffu,i;
    int fd=rh_p65_io_open(asset->path,1),got,rc=0;
    if(fd<0)return -2;
    while(used<asset->size){
        uint32_t wanted=asset->size-used;
        if(wanted>sizeof(bytes))wanted=sizeof(bytes);
        got=rh_p65_io_read(fd,bytes,wanted);
        if(got<=0||(uint32_t)got>wanted){rc=-74;break;}
        for(i=0;i<(uint32_t)got;i++){
            crc^=bytes[i];
            crc=(crc>>4)^crc_nibble[crc&15u];
            crc=(crc>>4)^crc_nibble[crc&15u];
        }
        used+=(uint32_t)got;
    }
    if(!rc&&(crc^0xffffffffu)!=asset->crc32)rc=-74;
    if(!rc&&rh_p65_io_read(fd,&extra,1)!=0)rc=-74;
    if(rh_p65_io_close(fd)&&!rc)rc=-5;
    return rc;
}
static int select_theme(uint32_t selected){
    unsigned i;int rc;uint32_t *slot=(uint32_t *)(uintptr_t)(RH_P65_FS_DRIVER+12u);
    if(rh_p65_io_identity())return -211;
    if(selected>2)return -22;
    if(!driver_owned())return -212;
    if(!*(volatile uint32_t *)(uintptr_t)0x3c45012cu||
       !*(volatile uint32_t *)(uintptr_t)0x3c450130u)return -213;
    if(selected){
        for(i=0;i<RH_P65_THEME_RULES;i++){
            rc=verify_asset(&rh_p65_theme_assets[selected-1u][i]);if(rc)return rc;
        }
        if(!load(&hooked)){
            if(!claim(slot,RH_P65_FS_OPEN,(uint32_t)(uintptr_t)hook_open))return -212;
            store(&hooked,1);
        }
    }
    /* io.close invokes this on the Lua/UI caller, not the NSH installer task.
     * No UI object traversal or guessed repaint ABI. Reopen the launcher after
     * a successful switch so stock objects rebind through the native decoder. */
    store(&mode,selected);
    for(i=0;i<RH_P65_THEME_RULES;i++){
        const struct rh_snapshot *snapshot=rh_p65_theme_snapshots[0];
        rc=rh_p65_cache_drop_path(rh_snapshot_pool(snapshot)+snapshot->rules[i].source_offset);
        if(rc){store(&mode,0);return -213;}
    }
    __atomic_fetch_add(&epoch,1,__ATOMIC_RELAXED);
    return 0;
}
static int control_close(void *file){
    struct client *c=client(file);uint32_t seq=0;int rc=0;
    if(!c)return -9;
    if(c->used||c->overflow){
        if(!claim(&writer,0,1))rc=-16;
        else{
            __atomic_fetch_add(&revision,1,__ATOMIC_ACQ_REL);
            if(c->used==RH_P65_CONTROL_BYTES)seq=word(c->command+4);
            if(c->overflow||c->used!=RH_P65_CONTROL_BYTES||!seq||
                word(c->command)!=RH_P65_CONTROL_MAGIC||word(c->command+12)!=0)rc=-22;
            else rc=select_theme(word(c->command+8));
            __atomic_store_n(&result,rc,__ATOMIC_RELEASE);store(&sequence,seq);
            __atomic_fetch_add(&revision,1,__ATOMIC_RELEASE);store(&writer,0);
        }
    }
    *file_private(file)=0;
    store(&c->allocated,0);
    return rc;
}
static int32_t control_write(void *file,const void *buffer,uint32_t count){
    struct client *c=client(file);uint32_t i;const uint8_t *b=buffer;
    if(!c||(!buffer&&count))return -9;
    if(count>RH_P65_CONTROL_BYTES-c->used){c->overflow=1;return -22;}
    for(i=0;i<count;i++)c->command[c->used+i]=b[i];
    c->used+=count;return (int32_t)count;
}
static int32_t control_read(void *file,void *buffer,uint32_t count){
    struct client *c=client(file);uint32_t n,i,before;uint8_t *out=buffer;
    if(!c||(!buffer&&count))return -9;
    if(!c->ready){
        before=load(&revision);if(before&1u)return -16;
        c->status[0]=RH_P65_STATUS_MAGIC;c->status[1]=1;c->status[2]=load(&mode);
        c->status[3]=load(&hooked);c->status[4]=load(&redirected);c->status[5]=load(&fallback);
        c->status[6]=load(&sequence);c->status[7]=(uint32_t)__atomic_load_n(&result,__ATOMIC_ACQUIRE);c->status[8]=load(&epoch);
        c->status[9]=(uint32_t)__atomic_load_n(&registration_result,__ATOMIC_ACQUIRE);c->status[10]=RH_P65_THEME_RULES;
        c->status[11]=RH_P65_MODULE_SCHEMA;
        if(load(&revision)!=before)return -16;
        c->ready=1;
    }
    n=RH_P65_STATUS_BYTES-c->cursor;if(n>count)n=count;
    for(i=0;i<n;i++)out[i]=((uint8_t *)c->status)[c->cursor+i];
    c->cursor+=n;return (int32_t)n;
}
static const file_operations operations={
    (void *)(uintptr_t)control_open,(void *)(uintptr_t)control_close,
    (void *)(uintptr_t)control_read,(void *)(uintptr_t)control_write,0,0,{0}
};
static int32_t retain_module(void *context){(void)context;return -16;}
__attribute__((used,section(".text.canopus_module_entry")))
int32_t rh_p65_theme_module_initialize(struct rh_p65_unload_pair *pair){
    int fd;unsigned i;
    if(!pair)return -22;pair->callback=0;pair->context=0;
    if(rh_p65_io_identity())return -211;
    init_receipt(1,0);
    if(!rh_p65_fs_driver_valid()){init_receipt(2,-212);return -212;}
    init_receipt(2,0);
    for(i=0;i<2;i++)if(snapshot_valid(i)){init_receipt(3,-214);return -214;}
    init_receipt(3,0);
    fd=rh_p65_io_open(RH_P65_DEVICE,1);
    if(fd>=0){rh_p65_io_close(fd);init_receipt(4,-217);return -217;}
    init_receipt(4,0);
    pair->callback=retain_module;
    /* Even a registration error must retain any escaped callback addresses.
     * The Lua client confirms the endpoint/schema; success of insmod alone is
     * not a registration or theme success receipt. No automatic retry. */
    __atomic_store_n(&registration_result,CANOPUS_SUP_REGISTER_DRIVER(RH_P65_DEVICE,&operations,0600,0),__ATOMIC_RELEASE);
    init_receipt(5,__atomic_load_n(&registration_result,__ATOMIC_ACQUIRE));
    return 0;
}
