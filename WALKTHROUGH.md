# EventVault-R: Complete Testing & Execution Walkthrough

This guide covers the full end-to-end flow: FPGA compilation, HPS-FPGA integration, board deployment, and benchmark execution.

---

## Part A: FPGA Synthesis (What You've Already Done)

1. Open Quartus Prime → `File → Open Project` → `fpga/quartus/eventvault_r.qpf`
2. Click **Start Compilation** (purple play button)
3. Verify the Fitter Summary shows ~1,032 ALMs (3.2%) and ~44 M10K blocks (11%)

---

## Part B: HPS-FPGA Integration (New — Platform Designer)

This is the step that actually connects the ARM processor to our FPGA accelerator.

### B1. Open Platform Designer
1. In Quartus, go to **Tools → Platform Designer** (or Qsys on older versions)

### B2. Add the HPS Component
1. In the IP Catalog (left panel), search for **"Arria V/Cyclone V Hard Processor System"**
2. Double-click to add it
3. In the configuration window:
   - **FPGA Interfaces tab:**
     - Enable **Lightweight HPS-to-FPGA bridge** (this is how the ARM talks to our registers)
     - Set its width to **32 bits**
   - **Peripheral Pins tab:**
     - Enable **UART0** (for serial console via PuTTY)
     - Enable **SD/MMC Controller** (for Linux boot)
     - Enable **USB1** (for USB peripherals)
     - Enable **Ethernet 0** (for SSH access)
     - Enable **SPI Master 1**, **I2C1**
   - **SDRAM tab:**
     - Enable **HPS-to-SDRAM** interface
     - Configure for **DDR3** matching DE1-SoC specs (1GB, 400 MHz, CAS latency 5)

### B3. Add Clock Source
1. Add a **Clock Source** from the IP Catalog
2. Set frequency to **50 MHz**
3. Connect its `clk` output to the HPS component's `f2h_axi_clock` and `h2f_lw_axi_clock`

### B4. Export the Signals
1. Right-click the HPS `memory` conduit → **Export** (name: `memory`)
2. Right-click the HPS `hps_io` conduit → **Export** (name: `hps_io`)
3. Right-click the HPS `h2f_lw_axi_master` → **Export** (name: `hps_0_h2f_lw_axi_master`)

### B5. Generate
1. Set the system name to **`soc_system`**
2. Click **Generate HDL...** → Select **Verilog** → Click **Generate**
3. This creates a `soc_system/` folder with all the bridge logic

### B6. Update the Quartus Project
1. In the `.qsf` file, change the top-level entity:
   ```
   set_global_assignment -name TOP_LEVEL_ENTITY de1_soc_top
   ```
2. Add the generated Qsys files:
   ```
   set_global_assignment -name QSYS_FILE soc_system.qsys
   ```
3. Add the new wrapper:
   ```
   set_global_assignment -name SYSTEMVERILOG_FILE ../rtl/de1_soc_top.sv
   ```
4. **Remove** the virtual pin assignments (we now have real pins!)
5. Import the DE1-SoC pin assignments from Terasic's golden `.qsf` file

### B7. Recompile
Click **Start Compilation**. This time it will compile the HPS + FPGA together.

---

## Part C: Prepare the DE1-SoC Board

### C1. Flash Linux to SD Card
1. Download the DE1-SoC Linux console image from [Terasic's DE1-SoC Resources page](https://www.terasic.com.tw/cgi-bin/page/archive.pl?No=836)
2. Use **balenaEtcher** or **Win32 Disk Imager** to flash it to a micro-SD card (≥4 GB)
3. Insert the SD card into the DE1-SoC's micro-SD slot

### C2. Connect Cables
- **USB Blaster** (Mini-USB) → for JTAG programming
- **UART-to-USB** (Mini-USB on the other port) → for serial console
- **Power** (12V barrel jack)
- **Ethernet** (optional, for SSH)

### C3. Program the FPGA
1. Open Quartus Programmer
2. Click **Auto Detect** → select `5CSEMA5`
3. Double-click the `5CSEMA5` row → select your new `.sof` file
4. Check **Program/Configure** → click **Start**
5. It should now succeed (no more 81% failure since the HPS is properly configured!)

### C4. Connect Serial Console
1. Open **PuTTY** (or any serial terminal)
2. Select **Serial**, set COM port (check Device Manager), baud rate **115200**
3. Click **Open** → you should see the Linux boot messages
4. Log in (default: `root`, no password)

---

## Part D: Run the Benchmark

### D1. Cross-Compile on Your PC
If you have the ARM cross-compiler installed:
```bash
arm-linux-gnueabihf-gcc -O2 -o hps_benchmark embedded/app/hps_benchmark.c -lm
```

If you do NOT have the cross-compiler, you can compile directly on the board:
1. Copy `embedded/app/hps_benchmark.c` to the SD card (or use `scp`)
2. On the board's Linux terminal:
   ```bash
   gcc -O2 -o hps_benchmark hps_benchmark.c -lm
   ```

### D2. Execute the Benchmark
```bash
sudo ./hps_benchmark
```

> **Note:** `sudo` is required because the program uses `/dev/mem` to access the FPGA bridge.

### D3. Record the Results
The program will print something like:
```
==================================================
 EventVault-R HPS-FPGA Benchmark
 Platform: DE1-SoC (Cyclone V, ARM Cortex-A9)
 Frame Size: 64 x 64 pixels
==================================================

[1] Software DWT (ARM Cortex-A9)
  Iterations: 100
  Total Time: 1523.45 ms
  Per Frame:  15.234 ms
  Frame Rate: 65.6 FPS
  Throughput: 0.269 Megapixels/sec

[2] Hardware DWT (FPGA via Lightweight Bridge)
  FPGA Cycles:     2750
  Per Frame:       0.055 ms
  Frame Rate:      18181.8 FPS
  Throughput:      74.473 Megapixels/sec
  Last L0 Value:   0x00A3F21C
  Guardrail Safe:  YES

==================================================
 RESULTS SUMMARY
==================================================
  ARM Software:     15.234 ms/frame  (65.6 FPS)
  FPGA Hardware:    0.055 ms/frame  (18181.8 FPS)
  Speedup Factor:   276.9x
  SW Throughput:    0.269 MP/s
  HW Throughput:    74.473 MP/s
==================================================
```

**Screenshot this output! These are your REAL, MEASURED results for the paper.**

---

## Part E: Generate Test Vectors (Python)

Before running the C++ executables, generate the golden vectors:
```bash
pip install -r requirements.txt
python verification/generate_vectors.py
```

---

## Part F: C++ Verification Suite

### Build (on PC)
```bash
cd embedded
build.bat
```

### Run Fixed-Point Evaluation (B16)
```bash
build\fixed_point_eval.exe
```
Records: RMSE, Max Error, Delta F, Delta x

### Run Saved Discovery Test (B17)
```bash
build\eventvault_app.exe
```
Records: Trigger frame, promoted frame count, escrow behavior
