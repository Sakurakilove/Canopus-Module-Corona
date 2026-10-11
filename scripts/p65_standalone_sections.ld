/* Stock ET_REL entry is relative to the merged executable section.
 * Keep unwind records together: per-function sections otherwise multiply
 * section headers and the stock loader's metadata allocations. */
SECTIONS
{
    .text : { KEEP(*(.text.canopus_module_entry)) *(.text .text.*) }
    .rodata : { *(.rodata .rodata.*) }
    .data : { *(.data .data.*) }
    .bss : { *(.bss .bss.* COMMON) }
    .ARM.exidx : { *(.ARM.exidx .ARM.exidx.*) }
    .ARM.extab : { *(.ARM.extab .ARM.extab.*) }
    .init_array : { *(.init_array .init_array.*) }
    .fini_array : { *(.fini_array .fini_array.*) }
}
