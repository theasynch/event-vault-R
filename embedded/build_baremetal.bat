@echo off
REM ============================================================
REM  build_baremetal.bat — Compile bare-metal ARM benchmark
REM
REM  Requirements:
REM    - ARM bare-metal toolchain (arm-none-eabi-gcc)
REM      Download: https://developer.arm.com/downloads/-/gnu-rm
REM      OR use the toolchain from Intel SoC EDS
REM
REM  If arm-none-eabi-gcc is not found, try arm-linux-gnueabihf-gcc
REM  with the -nostdlib flag (comes with SoC EDS).
REM ============================================================

echo.
echo ========================================
echo  Building Bare-Metal HPS Benchmark
echo ========================================
echo.

REM Try arm-none-eabi-gcc first (standard bare-metal toolchain)
where arm-none-eabi-gcc >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: arm-none-eabi-gcc
    set CC=arm-none-eabi-gcc
    set OBJCOPY=arm-none-eabi-objcopy
    goto compile
)

REM Try arm-linux-gnueabihf-gcc (from SoC EDS)
where arm-linux-gnueabihf-gcc >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Found: arm-linux-gnueabihf-gcc
    set CC=arm-linux-gnueabihf-gcc
    set OBJCOPY=arm-linux-gnueabihf-objcopy
    goto compile
)

REM Try looking in Intel SoC EDS default location
if exist "C:\intelFPGA\20.1\embedded\host_tools\mentor\gnu\arm\baremetal\bin\arm-none-eabi-gcc.exe" (
    echo Found: SoC EDS bare-metal toolchain
    set CC=C:\intelFPGA\20.1\embedded\host_tools\mentor\gnu\arm\baremetal\bin\arm-none-eabi-gcc.exe
    set OBJCOPY=C:\intelFPGA\20.1\embedded\host_tools\mentor\gnu\arm\baremetal\bin\arm-none-eabi-objcopy.exe
    goto compile
)

echo ERROR: No ARM cross-compiler found!
echo.
echo Please install one of:
echo   1. ARM GNU Toolchain (arm-none-eabi): https://developer.arm.com/downloads/-/gnu-rm
echo   2. Intel SoC EDS: https://www.intel.com/content/www/us/en/software-kit/develop
echo.
pause
exit /b 1

:compile
mkdir build 2>nul

echo Compiling hps_baremetal.c ...
%CC% -mcpu=cortex-a9 -mfloat-abi=hard -mfpu=neon ^
     -O2 -nostdlib -ffreestanding ^
     -Tbaremetal.ld ^
     -o build\hps_baremetal.elf ^
     app\hps_baremetal.c

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo FAILED: Compilation error!
    pause
    exit /b 1
)

echo Converting to binary...
%OBJCOPY% -O binary build\hps_baremetal.elf build\hps_baremetal.bin

echo.
echo ========================================
echo  BUILD SUCCESSFUL!
echo ========================================
echo  ELF: build\hps_baremetal.elf
echo  BIN: build\hps_baremetal.bin
echo.
echo  To load onto DE1-SoC via JTAG:
echo    1. Open Intel SoC EDS Command Shell
echo    2. Run: quartus_hps --cable=1 --addr=0xFFFF0000 -o GDBSERVER --preloader=build\hps_baremetal.bin
echo.
echo  OR use System Console (see WALKTHROUGH.md)
echo.
pause
