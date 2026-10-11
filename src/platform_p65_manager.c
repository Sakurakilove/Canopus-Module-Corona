/* Exact RW6/P65 icon-only manager platform. All graphics work runs on the
 * firmware LVGL owner task. No copied Band cache/object/font layouts. */
#include "resource_hook_platform.h"
#include "resource_hook_internal.h"
#include "resource_hook_target_p65.h"
#include "resource_hook_p65_io.h"
#include "resource_hook_p65_fs.h"
#include "resource_hook_p65_cache.h"
#include "resource_hook_font_reload.h"
#include "resource_hook_background.h"
#include "resource_hook_calendar_runtime.h"
#include "resource_hook_quickapp.h"
#include "p65_icon_sources.h"
#include "resource_hook_p65_paths.h"

int rh_platform_open(const char *p,int flags){return rh_p65_io_open(p,flags);}
int rh_platform_errno(void){return rh_p65_io_errno();}
int rh_platform_read(int fd,void *p,uint32_t n){return rh_p65_io_read(fd,p,n);}
int rh_platform_write(int fd,const void *p,uint32_t n){return rh_p65_io_write(fd,p,n);}
void rh_platform_close(int fd){(void)rh_p65_io_close(fd);}
void *rh_platform_alloc(uint32_t n){return ((void *(*)(uint32_t))(uintptr_t)RH_FW_ALLOC)(n);}
void rh_platform_free(void *p){if(p)((void (*)(void *))(uintptr_t)RH_FW_FREE)(p);}
uint32_t rh_platform_lock(void){uint32_t mask;__asm__ volatile("mrs %0,primask\ncpsid i":"=r"(mask)::"memory");return mask;}
void rh_platform_unlock(uint32_t mask){__asm__ volatile("msr primask,%0"::"r"(mask):"memory");}
void *rh_platform_driver(void){return (void *)(uintptr_t)RH_FW_POSIX_DRIVER;}
rh_open_fn *rh_platform_slot(void){return (rh_open_fn *)(uintptr_t)RH_FW_POSIX_OPEN_SLOT;}
rh_open_fn rh_platform_original(void){return (rh_open_fn)(uintptr_t)RH_FW_POSIX_OPEN;}
int rh_platform_driver_valid(void){
 const volatile uint32_t *d=(const volatile uint32_t *)(uintptr_t)RH_P65_FS_DRIVER;
 return (d[0]&255u)=='/'&&d[1]==0u&&d[3]&&(d[3]&1u)&&d[4]==RH_P65_FS_CLOSE&&
 d[5]==RH_P65_FS_READ&&d[6]==RH_P65_FS_WRITE&&d[7]==RH_P65_FS_SEEK&&d[8]==RH_P65_FS_TELL;
}
void *rh_platform_timer_create(uint32_t ms,void (*callback)(void *)){
    if(rh_p65_io_identity()||!callback||!ms)return 0;
    /* AP C7414D8: r0 callback -> +8; r1 period -> +0; r2 user -> +12. */
    return ((void *(*)(void (*)(void *),uint32_t,void *))(uintptr_t)RH_FW_TIMER_CREATE)(callback,ms,0);
}
void rh_platform_timer_delete(void *timer){
    /* C7752DA Lua timer deletion caller -> C74154C list unlink/free. */
    if(timer)((void (*)(void *))(uintptr_t)RH_FW_TIMER_DELETE)(timer);
}
int rh_platform_redraw_ready(void){return rh_platform_driver_valid();}
int rh_platform_retire_mapped_images(const struct rh_mapping_view *view){
    uint32_t i;char mapped[RH_PATH];int dropped=0;
    if(!view||!view->count)return 1;
    for(i=0;i<RH_P65_ICON_SOURCE_COUNT;i++){
        if(rh_resolve_view(view,rh_p65_icon_sources[i],mapped)!=1)continue;
        if(rh_p65_cache_drop_path(rh_p65_icon_sources[i]))return -1;
        dropped=1;
    }
    return dropped?0:1;
}
int rh_platform_retire_images(const struct rh_state *s){struct rh_mapping_view v=rh_rules_view(s->rules,s->count);return rh_platform_retire_mapped_images(&v);}
/* Owner objects refresh naturally when reopening their page. module.c leaves
 * redraw/rebuild counters at zero for this target rather than fabricating it. */
int rh_platform_refresh_mapped_images(const struct rh_mapping_view *old,const struct rh_mapping_view *current){(void)old;(void)current;return 0;}
int rh_platform_refresh_images(const struct rh_state *s){(void)s;return 0;}
int rh_platform_request_full_redraw(void){return -1;}
/* Optional features are explicitly unsupported by this icon product. */
int rh_platform_font_path_get(uint32_t i,char *name,char *path){(void)i;if(name)name[0]=0;if(path)path[0]=0;return -1;}
int rh_platform_font_retarget(uint32_t i,const char *path){(void)i;(void)path;return -2150;}
int rh_font_reload(const struct rh_mapping_view *v,uint32_t *changed){
    uint32_t i;
    if(changed)*changed=0;
    for(i=0;v&&i<v->count;i++){
        const char *source=v->snapshot?rh_snapshot_pool(v->snapshot)+v->snapshot->rules[i].source_offset:v->rules[i].source;
        if(!rh_p65_icon_source_allowed(source))return -2150;
    }
    return 0;
}
void rh_font_reload_disable(void){}
int rh_platform_quickapp_icon_path(const char *package,char out[RH_PATH]){(void)package;if(out)out[0]=0;return -2;}
int rh_platform_calendar_affected(const struct rh_mapping_view *a,const struct rh_mapping_view *b){(void)a;(void)b;return 0;}
int rh_platform_refresh_calendar(void){return 0;}
int rh_platform_calendar_retire(const struct rh_calendar_config *c){(void)c;return 0;}
void rh_platform_calendar_publish(void){}
int rh_calendar_stage(struct rh_calendar_config **out){if(out)*out=0;return 0;}
int rh_calendar_commit(struct rh_calendar_config *c){(void)c;return -2151;}
void rh_calendar_discard(struct rh_calendar_config *c){(void)c;}
int rh_calendar_start(void){return 0;}
int rh_calendar_refresh(void){return 0;}
int rh_calendar_poll(void){return 0;}
int rh_calendar_pending(void){return 0;}
const char *rh_calendar_redirect(const char *path){(void)path;return 0;}
int rh_platform_backgrounds_stage(const struct rh_backgrounds *b){return b&&(b->launcher[0]||b->control_center[0]||b->notifications[0]||b->widgets[0])?-2152:0;}
int rh_platform_backgrounds_commit(const struct rh_backgrounds *b){return rh_platform_backgrounds_stage(b);}
void rh_platform_backgrounds_poll(void){}
