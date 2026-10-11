/* Offline-audited P65 file I/O only. This is not an LVGL platform adapter. */
#ifndef RESOURCE_HOOK_P65_IO_H
#define RESOURCE_HOOK_P65_IO_H
#include <stdint.h>
#define RH_P65_TARGET_ID "xiaomi-p65-3.100.043"
#define RH_P65_AP_SHA256 "a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858"
int rh_p65_io_identity(void);
int rh_p65_io_open(const char *path, int mode);
int rh_p65_io_read(int fd, void *buffer, uint32_t size);
int rh_p65_io_write(int fd, const void *buffer, uint32_t size);
int rh_p65_io_close(int fd);
int rh_p65_io_errno(void);
#endif
