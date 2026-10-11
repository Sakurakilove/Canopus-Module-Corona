/* Freestanding memory primitives: no dependency on firmware exports. */
#include <stdint.h>
void __aeabi_memcpy(void *destination,const void *source,uint32_t count) {
    uint8_t *d=destination;const uint8_t *s=source;
    while(count--)*d++=*s++;
}
void __aeabi_memcpy4(void *d,const void *s,uint32_t n){__aeabi_memcpy(d,s,n);}
void __aeabi_memcpy8(void *d,const void *s,uint32_t n){__aeabi_memcpy(d,s,n);}
void __aeabi_memset(void *destination,uint32_t count,int value){
    uint8_t *d=destination;while(count--)*d++=(uint8_t)value;
}
void __aeabi_memclr(void *d,uint32_t n){__aeabi_memset(d,n,0);}
void __aeabi_memclr4(void *d,uint32_t n){__aeabi_memset(d,n,0);}
void __aeabi_memclr8(void *d,uint32_t n){__aeabi_memset(d,n,0);}
