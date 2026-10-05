arm-none-eabi-gcc -mcpu=cortex-a9 -mfloat-abi=hard -mfpu=neon -O2 -nostdlib -Tbaremetal.ld -o hps_baremetal.elf hps_baremetal.c
