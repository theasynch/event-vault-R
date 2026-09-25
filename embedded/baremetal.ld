/* Bare-metal linker script for Cyclone V SoC ARM Cortex-A9 */
/* Targets the on-chip RAM (OCRAM) at 0xFFFF0000, 64 KB         */
/* No external DDR3 needed — runs entirely from OCRAM            */

ENTRY(_start)

MEMORY
{
    /* On-Chip RAM: 64 KB starting at 0xFFFF0000 */
    OCRAM (rwx) : ORIGIN = 0xFFFF0000, LENGTH = 64K
}

SECTIONS
{
    . = ORIGIN(OCRAM);

    .text : {
        *(.text.startup)    /* _start entry point */
        *(.text*)           /* All other code */
    } > OCRAM

    .rodata : {
        *(.rodata*)         /* Read-only data (strings, constants) */
    } > OCRAM

    .data : {
        *(.data*)           /* Initialized global data */
    } > OCRAM

    .bss : {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        __bss_end = .;
    } > OCRAM

    /* Stack grows downward from top of OCRAM */
    _stack_top = ORIGIN(OCRAM) + LENGTH(OCRAM);
}
