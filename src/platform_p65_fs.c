/* Read-only driver probe and explicit-open adapter for caller-owned offline
 * state. No callback replacement, initializer, cache/graphics mutation or
 * installable module descriptor. Opening is only done by rh_p65_fs_open. */
#include "resource_hook_p65_fs.h"
#include "resource_hook_p65_io.h"
#include "resource_hook.h"
int rh_p65_fs_driver_valid(void) {
    const volatile uint32_t *driver;
    if (rh_p65_io_identity()) return 0;
    driver = (const volatile uint32_t *)(uintptr_t)RH_P65_FS_DRIVER;
    return (driver[0] & 0xffu) == '/' &&
        driver[1] == RH_P65_FS_CACHE_BYTES &&
        driver[3] == RH_P65_FS_OPEN && driver[4] == RH_P65_FS_CLOSE &&
        driver[5] == RH_P65_FS_READ && driver[6] == RH_P65_FS_WRITE &&
        driver[7] == RH_P65_FS_SEEK && driver[8] == RH_P65_FS_TELL;
}
int rh_p65_fs_prepare_state(struct rh_state *state) {
    if (!state || state->installed || !rh_p65_fs_driver_valid()) return -1;
    state->driver=(void *)(uintptr_t)RH_P65_FS_DRIVER;
    state->original=(rh_open_fn)(uintptr_t)RH_P65_FS_OPEN;
    return 0;
}
int rh_p65_fs_open(struct rh_state *state, const char *path, int mode) {
    if (!state || rh_p65_io_identity() ||
        state->driver!=(void *)(uintptr_t)RH_P65_FS_DRIVER ||
        state->original!=(rh_open_fn)(uintptr_t)RH_P65_FS_OPEN) return 0;
    return rh_posix_open(state,state->driver,path,mode);
}
