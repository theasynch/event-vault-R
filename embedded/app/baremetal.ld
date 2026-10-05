MEMORY
{
    OCRAM (rwx) : ORIGIN = 0xFFFF0000, LENGTH = 64K
}

SECTIONS
{
    .text : {
        /* Ensure startup code (like _start) is placed first */
        *(.text.startup)
        *(.text*)
        *(.rodata*)
    } > OCRAM

    .data : {
        *(.data*)
    } > OCRAM

    .bss : {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        __bss_end = .;
    } > OCRAM
}
