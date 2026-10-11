#include "resource_hook_p65_cache.h"
#include "resource_hook_p65_io.h"
#include <stdint.h>

int rh_p65_cache_drop_path(const char *path)
{
    static const char prefix[] = "/resource/app/";
    unsigned i, n;
    if (!path || rh_p65_io_identity()) return -1;
    for (i=0; prefix[i]; ++i) if (path[i] != prefix[i]) return -1;
    for (n=i; n<256 && path[n]; ++n) {
        unsigned char ch=(unsigned char)path[n];
        if (!((ch>='a' && ch<='z') || (ch>='A' && ch<='Z') || (ch>='0' && ch<='9') ||
              ch=='_' || ch=='/' || ch=='.')) return -1;
        if (ch=='.' && path[n+1]=='.') return -1;
    }
    if (n>=256 || n<i+5 || path[n-4]!='.' || path[n-3]!='b' ||
        path[n-2]!='i' || path[n-1]!='n') return -1;
    if (!*(const volatile uint32_t *)(uintptr_t)0x3c45012cu ||
        !*(const volatile uint32_t *)(uintptr_t)0x3c450130u) return -1;
    /* Native lv_image_cache_drop(path) constructs separate 24-byte header and
     * decoded keys, sets the source type, and calls cache_drop(cache,key,NULL).
     * It uses cache-native locking/refcount retirement. Do not transplant the
     * Band's manual list offsets or the two-argument cache_drop cast. */
    ((void (*)(const char *))(uintptr_t)0x0c73bca5u)(path);
    return 0;
}
