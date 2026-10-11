#ifndef RESOURCE_HOOK_P65_FS_H
#define RESOURCE_HOOK_P65_FS_H
#include <stdint.h>
/* Exact 3.100.043 AP initializer at 0x0c7358f4. Read-only inspection;
 * this does not install a hook or authorize native module deployment. */
#define RH_P65_FS_DRIVER 0x3c4501d0u
#define RH_P65_FS_DRIVER_BYTES 52u
#define RH_P65_FS_CACHE_BYTES 0u
#define RH_P65_FS_OPEN 0x0c7357d5u
#define RH_P65_FS_CLOSE 0x0c735789u
#define RH_P65_FS_READ 0x0c735739u
#define RH_P65_FS_WRITE 0x0c7356e9u
#define RH_P65_FS_SEEK 0x0c73589du
#define RH_P65_FS_TELL 0x0c735691u
int rh_p65_fs_driver_valid(void);
struct rh_state;
/* Caller-owned offline state; neither function replaces a firmware callback.
 * Installation, immutable runtime snapshots and UI ownership remain unwired. */
int rh_p65_fs_prepare_state(struct rh_state *);
int rh_p65_fs_open(struct rh_state *, const char *, int);
#endif
