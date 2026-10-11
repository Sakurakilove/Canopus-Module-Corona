#ifndef RESOURCE_HOOK_P65_STANDALONE_H
#define RESOURCE_HOOK_P65_STANDALONE_H
#include <stdint.h>
#define RH_P65_DEVICE "/dev/rw6-corona-v1"
#define RH_P65_STATUS_MAGIC 0x48543652u /* R6TH */
#define RH_P65_CONTROL_MAGIC 0x43365452u /* RT6C */
#define RH_P65_STATUS_WORDS 12u
#define RH_P65_STATUS_BYTES 48u
#define RH_P65_CONTROL_BYTES 16u
#define RH_P65_MODULE_SCHEMA 0x00030005u
/* Control: magic, nonzero sequence, mode (0=stock,1=orbit,2=fold), reserved=0.
 * Commands run only at close of a complete frame. Status: magic/schema/mode/
 * hook/redirect/fallback/sequence/signed-result/epoch/register-result/count/
 * module-schema. Buffers are bounded per opened file; EOF is supported. */
struct rh_p65_unload_pair { int32_t (*callback)(void *); void *context; };
int32_t rh_p65_theme_module_initialize(struct rh_p65_unload_pair *);
#endif
