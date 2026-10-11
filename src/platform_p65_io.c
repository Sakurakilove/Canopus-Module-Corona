/* Exact P65 3.100.043 AP I/O port. No initializer, driver mutation, graphics
 * calls, autoload or installable module descriptor. For offline ABI tests.
 * The renderer/open-slot/cache ABI still needs independent recovery. */
#include "resource_hook_p65_io.h"
#include "canopus_p65_abi.h"
#include "canopus_veneer.h"

int rh_p65_io_identity(void) { return canopus_identity_guard(); }
int rh_p65_io_open(const char *path, int mode) {
    if (rh_p65_io_identity() || !path) return -1;
    /* Supply mode_t for P65's O_CREAT (bit 2), even if the file exists. */
    return ((int (*)(const char *, int, ...))(uintptr_t)CANOPUS_SUP_NUTTX_OPEN)
        (path, mode, 0600);
}
int rh_p65_io_read(int fd, void *buffer, uint32_t size) {
    if (rh_p65_io_identity() || (!buffer && size)) return -1;
    return ((int (*)(int, void *, uint32_t))(uintptr_t)CANOPUS_SUP_NUTTX_READ)
        (fd, buffer, size);
}
int rh_p65_io_write(int fd, const void *buffer, uint32_t size) {
    if (rh_p65_io_identity() || (!buffer && size)) return -1;
    /* Shared Canopus exact-AP binding: plain write, never pwrite. */
    return ((int (*)(int, const void *, uint32_t))(uintptr_t)CANOPUS_SUP_NUTTX_WRITE)
        (fd, buffer, size);
}
int rh_p65_io_close(int fd) {
    if (rh_p65_io_identity()) return -1;
    return ((int (*)(int))(uintptr_t)CANOPUS_SUP_NUTTX_CLOSE)(fd);
}
int rh_p65_io_errno(void) {
    const int *value;
    if (rh_p65_io_identity()) return 0;
    value = ((int *(*)(void))(uintptr_t)CANOPUS_SUP_NUTTX_ERRNO_LOCATION)();
    return value ? *value : 0;
}
