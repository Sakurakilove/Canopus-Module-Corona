#ifndef RESOURCE_HOOK_P65_CACHE_H
#define RESOURCE_HOOK_P65_CACHE_H
/* Exact P65 native source-path invalidation; offline-tested, not yet called by
 * a device module. Returns 0 on dispatch, -1 on identity/path/init rejection. */
int rh_p65_cache_drop_path(const char *);
#endif
