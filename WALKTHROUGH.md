# EventVault-R: Complete Testing & Execution Walkthrough

This guide provides a comprehensive step-by-step process for compiling the FPGA hardware, deploying it to your DE1-SoC board, and running the software verification and profiling tools.

## 1. Quartus Synthesis (Hardware Compilation)

We have heavily optimized the RTL in Phase C so it fits cleanly into the DE1-SoC logic fabric. 

1. **Open Quartus Prime:** Launch Intel Quartus Prime on your Windows machine.
2. **Open Project:** Go to `File -> Open Project` and navigate to `fpga/quartus/eventvault_r.qpf`.
3. **Start Compilation:** Click the **Start Compilation** button (the purple play button) in the top toolbar.
4. **Verify Resources:** Once complete, check the Compilation Report. The Fitter section should now show Logic Array Blocks (LABs) well below the 3207 limit, and M10K memory block utilization should be clearly visible.

## 2. Deploying to the DE1-SoC (FPGA Bitstream)

You need to load the compiled hardware `.sof` file onto the FPGA side of the DE1-SoC board.

1. **Connect the Board:** Ensure your DE1-SoC is powered on and connected to your PC via the USB Blaster port.
2. **Open Programmer:** In Quartus, go to `Tools -> Programmer`.
3. **Hardware Setup:** Click `Hardware Setup` in the top left and select `DE-SoC [USB-1]`.
4. **Add File:** If `eventvault_r.sof` isn't listed, click `Add File` and select `fpga/quartus/output_files/eventvault_r.sof`.
5. **Program:** Check the `Program/Configure` box next to the file, and hit **Start**. The progress bar in the top right will hit 100% (Successful). 

## 3. Preparing the Test Vectors (Software)

Before running the C++ tools, you need to generate the synthetic astronomical frame data that the C++ tests will read.

1. Open your terminal in the `event-vault-R` root folder.
2. Run the vector generation script:
   ```bash
   python verification/generate_vectors.py
   ```
   This will generate the required binary files (like `saved_discovery_frames.bin`) inside `verification/vectors/`.

## 4. Building the C++ Verification Suite

You can compile the C++ software on your Windows PC using MinGW (as we set it up earlier) to run the simulation/verification. If you want to run this on the DE1-SoC's ARM processor, you can use `scp` to copy the `embedded/` folder to the board and run `make` there.

1. Open your terminal and navigate to the embedded folder:
   ```bash
   cd embedded
   ```
2. Generate the build files and compile the suite using CMake (this automatically detects your lab machine's C++ compiler like Visual Studio or MinGW):
   ```bash
   mkdir build
   cd build
   cmake ..
   cmake --build . --config Release
   ```
   This generates the executables in `embedded/build/` (or `embedded/build/Release/` if using Visual Studio): `test_dwt.exe`, `fixed_point_eval.exe`, and `eventvault_app.exe`.

## 5. Running the Tests & Recording Results

### Task B16: Rate-Distortion Sweep
To evaluate the fixed-point distortion versus floating-point, use the `fixed_point_eval.exe` tool. This tool runs the entire image through both float and fixed-point pipelines and outputs the Mean Squared Error (MSE).

1. In the `embedded/` directory, run:
   ```bash
   build\fixed_point_eval.exe
   ```
2. **Recording Results:** The console will print out the RMSE (Root Mean Square Error) between the theoretical C++ floating-point DWT and the fixed-point Q16.16 DWT logic that mirrors the FPGA. Record this RMSE value for your documentation. The RMSE should be practically 0 (or exactly 0) due to our recent fixes.

### Task B17: Performance Profiling
To test the overall system logic (trigger mechanics, escrow buffering, and event promotion), use `eventvault_app.exe`.

1. Run the app:
   ```bash
   build\eventvault_app.exe
   ```
2. **Recording Results:** The tool will process 50 frames. It is configured to detect a transient event at frame 25. You will see the console output state that the trigger fired at frame 25, and it will subsequently dump the escrowed/promoted frames (e.g., frames 15 to 35). Record the output log to prove the system correctly caches and promotes history surrounding a trigger event.

---

> [!TIP]
> If you run into any "File not found" errors when running the `.exe` files, ensure you are running them from the `embedded/` directory (not `embedded/build/`) so the relative paths to `../verification/vectors/` resolve correctly.
