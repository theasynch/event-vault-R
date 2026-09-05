# EventVault-R — Phase B & Phase C Implementation Roadmap

## Purpose

Phase A of EventVault-R is complete.

Phase A is the **Python reference implementation** and will now be treated as the **golden reference model** for all future development.

The next two phases transform the same EventVault-R algorithms into:

```text
PHASE A
Python Reference Model
        |
        | Golden outputs / test vectors
        v
PHASE B
Embedded C/C++
        |
        | Validated against Python
        v
DE1-SoC ARM HPS
        |
        v
PHASE C
FPGA / RTL Acceleration
        |
        v
Integrated DE1-SoC System
        |
        v
TRL-4 Laboratory Demonstrator
```

The most important rule throughout both phases is:

> **Do not rewrite EventVault-R conceptually. Implement the same verified behavior at progressively lower implementation levels.**

---

# 1. The role of Phase A

The current Python repository is the **golden reference**.

It already contains the major functional modules:

```text
eventvault/
├── acquisition/
├── codec/
├── science/
├── escrow/
├── uncertainty/
├── resource/
├── telemetry/
└── pipeline.py

experiments/
├── rate_distortion.py
└── saved_discovery.py

tests/
```

Phase A answers:

> **What should EventVault-R do?**

Phase B asks:

> **Can the same behavior be implemented deterministically in embedded C/C++?**

Phase C asks:

> **Which computational kernels should be moved into FPGA hardware, and can they reproduce the verified behavior?**

---

# 2. Repository structure for Phase B and C

Do not destroy or replace the current Python implementation.

Add the following directories:

```text
event-vault-R/
|
├── eventvault/                 # PHASE A — Python golden model
│
├── experiments/               # Existing Phase-A experiments
│
├── tests/                     # Existing Phase-A tests
│
├── embedded/                  # PHASE B
│   ├── include/
│   ├── src/
│   ├── tests/
│   ├── app/
│   └── CMakeLists.txt
│
├── verification/              # Cross-platform verification
│   ├── vectors/
│   ├── python_vs_cpp/
│   ├── cpp_vs_fpga/
│   └── reports/
│
└── fpga/                      # PHASE C
    ├── rtl/
    │   ├── dwt/
    │   ├── guardrail/
    │   ├── buffers/
    │   └── interfaces/
    ├── tb/
    ├── quartus/
    └── software/
```

The Python model remains the reference throughout the entire project.

---

# PHASE B — EMBEDDED C/C++ IMPLEMENTATION

## Phase-B objective

Convert the Python EventVault-R reference implementation into deterministic embedded software suitable for an embedded ARM/RISC-V-class processor.

The Phase-B implementation must be:

- deterministic,
- memory-bounded,
- numerically controlled,
- free from unnecessary dynamic allocation,
- portable,
- independently testable,
- verifiable against the Python reference.

The initial development target is a normal PC.

The final Phase-B deployment target is the **ARM HPS of the Terasic DE1-SoC**.

---

# B1 — Create the C++ project skeleton

Create:

```text
embedded/
├── include/
│   ├── dwt.hpp
│   ├── guardrail.hpp
│   ├── escrow.hpp
│   ├── uncertainty.hpp
│   ├── resource_controller.hpp
│   ├── telemetry.hpp
│   └── pipeline.hpp
│
├── src/
│   ├── dwt.cpp
│   ├── guardrail.cpp
│   ├── escrow.cpp
│   ├── uncertainty.cpp
│   ├── resource_controller.cpp
│   ├── telemetry.cpp
│   └── pipeline.cpp
│
├── app/
│   └── main.cpp
│
└── tests/
```

Use:

- C++17
- CMake
- GCC during host development

### Definition of done

```text
cmake ..
cmake --build .
```

must successfully generate the EventVault-R C++ executable.

At this stage, there does not need to be a complete implementation.

The goal is simply to establish the build system and module boundaries.

---

# B2 — Port the DWT

The first major functional port is:

```text
eventvault/codec/dwt.py
            |
            v
embedded/src/dwt.cpp
embedded/include/dwt.hpp
```

The functional behavior must remain the same:

```text
Input Image
     |
     v
3-Level DWT
     |
     +--> L0
     +--> H1
     +--> H2
     +--> H3
```

Initially:

> **Use floating-point C++ arithmetic.**

Do not introduce fixed-point yet.

The first objective is to prove:

```text
Python DWT
      ≈
C++ floating-point DWT
```

---

# B3 — Create Python golden vectors

The Python reference will generate deterministic input/output test vectors.

Create:

```text
verification/vectors/
├── image_001.bin
├── image_002.bin
├── l0_001.bin
├── h1_001.bin
├── h2_001.bin
├── h3_001.bin
└── metadata_001.json
```

For each vector record:

- input image,
- wavelet type,
- image dimensions,
- expected coefficient arrays,
- expected reconstructed image,
- reference measurements.

Use deterministic random seeds.

### Definition of done

A C++ test can consume the same input vector and compare its output against the Python result.

---

# B4 — Verify C++ floating-point DWT against Python

Run the same input through:

```text
              SAME INPUT
                  |
        +---------+---------+
        |                   |
        v                   v
      Python               C++
      Golden              Floating
      Model               Point
        |                   |
        +---------+---------+
                  |
                  v
               Compare
```

Compare:

- L0
- H1
- H2
- H3
- reconstructed image

Calculate:

```text
maximum absolute error
mean absolute error
RMS error
```

### Definition of done

The C++ implementation must remain within the defined numerical tolerance relative to Python.

---

# B5 — Introduce fixed-point arithmetic

Once the floating-point C++ DWT matches Python:

```text
C++ floating point
        |
        v
C++ fixed point
```

The fixed-point format must be chosen experimentally.

Do not arbitrarily select a Q-format.

Measure:

```text
minimum coefficient
maximum coefficient
dynamic range
required precision
accumulator range
```

Then evaluate candidate formats such as:

```text
Q8.8
Q16.16
```

or another format justified by the measured signal range.

---

# B6 — Validate fixed-point scientific accuracy

Run:

```text
Python floating-point
        |
        v
C++ fixed-point
        |
        v
Science measurements
```

Measure:

```text
ΔF
Δx
reconstruction error
coefficient error
```

The existing EventVault-R science targets are:

```text
Photometric error:
ΔF <= 0.5%

Centroid error:
Δx <= 0.1 pixel
```

The chosen fixed-point representation must not cause the embedded implementation to violate the required scientific tolerances for the tested operating envelope.

### Definition of done

Produce a report containing:

```text
Q-format
word length
maximum error
RMS error
ΔF error
Δx error
```

---

# B7 — Port the Science Guardrail

Translate:

```text
eventvault/science/guardrail.py
```

into:

```text
embedded/src/guardrail.cpp
embedded/include/guardrail.hpp
```

The mathematical behavior remains:

```text
Remove layer
      |
      v
Reconstruct
      |
      v
Measure source
      |
      +----------------------+
      |                      |
      v                      v
Within bounds?           Outside bounds?
      |                      |
      v                      v
SAFE TO DROP              LOCK
```

Implement:

- flux calculation,
- centroid calculation,
- photometric error,
- centroid error,
- threshold comparison,
- layer lock/unlock decision.

---

# B8 — Port the escrow system

Translate the Python escrow system:

```text
eventvault/escrow/
├── buffer.py
├── entry.py
└── promotion.py
```

into:

```text
embedded/
├── include/
│   ├── escrow.hpp
│   └── escrow_entry.hpp
│
└── src/
    ├── escrow.cpp
    └── promotion.cpp
```

The embedded implementation should use static memory.

Conceptually:

```text
EscrowEntry escrow_buffer[MAX_ENTRIES];
```

Avoid uncontrolled heap allocation.

---

# B9 — Implement the escrow state machine

Each residual layer should have an explicit state.

Recommended conceptual states:

```text
NEW
 |
 v
ESCROW
 |
 +------------------+
 |                  |
 v                  v
SAFE_TO_PURGE     LOCKED
                     |
                     v
                  PROMOTED
```

Implement explicit state transitions.

Verify:

- push,
- lock,
- unlock,
- promotion,
- expiry,
- purge,
- overflow handling.

### Critical requirement

The system must never silently overwrite protected information.

If the buffer is full and no safe entry can be evicted:

```text
ERROR / OVERFLOW STATE
```

rather than silent data loss.

---

# B10 — Port uncertainty estimation

Translate:

```text
eventvault/uncertainty/
├── estimator.py
└── retention.py
```

Initially keep uncertainty processing on the CPU.

Implement:

- softmax entropy,
- Mahalanobis distance,
- normalized uncertainty score,
- retention-priority calculation.

The central policy must remain:

```text
Higher uncertainty
        |
        v
Higher retention priority
```

The system must not interpret model uncertainty as evidence that the observation is safe to discard.

---

# B11 — Port the resource controller

Translate:

```text
eventvault/resource/controller.py
```

into C++.

The controller monitors:

```text
M_free
B_downlink
E_batt
```

and adjusts:

```text
T_h
τ_snr
D_min
```

The first embedded version should remain deterministic and rule-based.

Do not introduce reinforcement learning or complex optimization yet.

---

# B12 — Port telemetry and scheduling

Translate:

```text
eventvault/telemetry/downlink.py
```

into the embedded environment.

Implement:

```text
Base layer
     ↓
Priority queue

Promoted residuals
     ↓
High-priority queue

Normal residuals
     ↓
Lower-priority queue
```

The simulated downlink can remain a file/socket interface during host development.

---

# B13 — Rebuild the complete EventVault-R C++ pipeline

At this point:

```text
Frame
  |
  v
Calibration
  |
  v
DWT
  |
  v
Source Extraction
  |
  v
Science Guardrail
  |
  v
Uncertainty
  |
  v
Escrow
  |
  v
Resource Controller
  |
  v
Promotion
  |
  v
Telemetry
```

The C++ application should now process the same Saved Discovery sequence used by Phase A.

---

# B14 — Cross-validate the complete pipeline

Use the same inputs for:

```text
Python
C++
```

Compare:

```text
Frame count
DWT results
Flux
Centroid
Guardrail decision
Uncertainty
Escrow states
Promoted frames
Purged frames
Downlink ordering
```

The strongest goal is:

> **Equivalent system decisions, not merely similar individual function outputs.**

---

# B15 — Re-run the Saved Discovery experiment in C++

The C++ version must reproduce the Phase-A scenario:

```text
60 frames
30-second cadence
Transient starts: T10
Detection: T25
```

Expected behavior:

```text
T10-T24
    |
    v
Escrow

T25
    |
    v
Trigger
    |
    v
Retroactive promotion
    |
    v
T10-T24 recovered
```

Compare the C++ result against the Python reference.

---

# B16 — Re-run Rate-Distortion in C++

Repeat:

```text
Compression Ratio
        vs
Photometric Error

Compression Ratio
        vs
Centroid Error
```

Compare:

```text
Python
vs
C++ floating point
vs
C++ fixed point
```

---

# B17 — Profile the C++ implementation

Measure:

```text
Execution time / frame
Memory consumption
CPU utilisation
Maximum buffer size
Escrow occupancy
Throughput
```

Create a table:

```text
Metric                  Result
---------------------------------------
Frame processing time   ______ ms
Peak RAM                ______ MB
DWT time                ______ ms
Guardrail time          ______ ms
Escrow processing       ______ ms
Throughput              ______ fps
```

These become the Phase-B baseline.

---

# B18 — Deploy the C++ implementation onto DE1-SoC ARM HPS

Target hardware:

> **Terasic DE1-SoC ARM HPS**

The first DE1-SoC milestone is:

```text
DE1-SoC
   |
   v
ARM HPS
   |
   v
C++ EventVault-R
```

Do not use the FPGA yet.

Treat the DE1-SoC as an embedded computer first.

The FPGA fabric is intentionally unused during this milestone.

---

# B19 — Benchmark EventVault-R on the ARM HPS

Repeat the same benchmark from B17.

Measure:

```text
Frame processing time
Memory usage
CPU utilization
Escrow behavior
Throughput
Power, if measurement equipment is available
```

Now you have:

```text
PC
vs
DE1-SoC ARM
```

performance data.

---

# B20 — Phase-B definition of done

Phase B is complete when:

- C++ builds reproducibly.
- C++ DWT matches the Python reference within defined numerical tolerance.
- Fixed-point DWT satisfies scientific tolerances.
- Science Guardrail matches Python behavior.
- Escrow behavior matches Python behavior.
- Promotion behavior matches Python behavior.
- Saved Discovery executes successfully.
- Rate-Distortion experiment runs successfully.
- The complete pipeline runs on the DE1-SoC ARM HPS.
- Timing and memory are measured.

At that point:

> **Phase B proves that EventVault-R can exist as deterministic embedded software.**

---

# PHASE C — FPGA / RTL ACCELERATION

## Phase-C objective

Do NOT implement the entire EventVault-R system in RTL.

Instead:

> **Move the most repetitive and computationally deterministic signal-processing kernels into the FPGA fabric while leaving high-level control on the ARM processor.**

The target board is:

> **Terasic DE1-SoC**

The target architecture is:

```text
                     DE1-SoC
┌──────────────────────────────────────────────┐
│                                              │
│              ARM HPS                         │
│                                              │
│  EventVault Controller                       │
│  Escrow Manager                              │
│  Uncertainty                                 │
│  Resource Controller                         │
│  Telemetry                                   │
│       |                                      │
│       | AXI                                  │
│       v                                      │
│  ┌────────────────────────────────────────┐  │
│  │           FPGA FABRIC                  │  │
│  │                                        │  │
│  │   ┌──────────────┐  ┌──────────────┐  │  │
│  │   │ DWT IP       │  │ Guardrail IP │  │  │
│  │   │              │  │              │  │  │
│  │   └──────────────┘  └──────────────┘  │  │
│  │                                        │  │
│  └────────────────────────────────────────┘  │
│                                              │
│                 DDR3 / Memory                │
└──────────────────────────────────────────────┘
```

---

# C1 — Freeze the C++ interfaces

Before RTL work begins, freeze:

- input data format,
- coefficient format,
- fixed-point representation,
- layer representation,
- guardrail threshold representation,
- control/status interface.

Do not simultaneously change the C++ algorithm and RTL architecture.

The C++ implementation becomes the next reference layer.

---

# C2 — Generate FPGA golden vectors

Take the verified C++ / Python test vectors and create:

```text
verification/vectors/
├── dwt_input_001.bin
├── dwt_expected_l0_001.bin
├── dwt_expected_h1_001.bin
├── dwt_expected_h2_001.bin
├── dwt_expected_h3_001.bin
│
├── guardrail_input_001.bin
└── guardrail_expected_001.json
```

Each vector should have a known expected result.

---

# C3 — Create the FPGA project

Create:

```text
fpga/
├── rtl/
│   ├── dwt/
│   ├── guardrail/
│   ├── buffers/
│   └── interfaces/
│
├── tb/
│   ├── dwt_tb.sv
│   └── guardrail_tb.sv
│
├── quartus/
└── software/
```

Use:

- Intel Quartus Prime
- SystemVerilog
- appropriate DE1-SoC target device/settings
- ModelSim/Questa or the simulator available in the setup
- Platform Designer where appropriate

---

# C4 — Implement the 1-D DWT lifting block

Do not begin with a complete 2-D image processor.

First implement:

```text
1-D input
   |
   v
Predict
   |
   v
Update
   |
   v
Scale
   |
   +---- Low-pass
   |
   +---- High-pass
```

Verify this independently.

---

# C5 — Implement line buffering

A 2-D DWT requires storage for image rows/columns.

Create:

```text
line_buffer.sv
```

The hardware should support streaming or block-based image processing.

First optimize for correctness.

---

# C6 — Implement the 2-D DWT

Combine:

```text
Horizontal DWT
      +
Vertical DWT
```

to generate:

```text
L0
LH
HL
HH
```

Then extend this to the required three levels.

---

# C7 — Simulate the DWT RTL

Feed the same golden vectors used by Python/C++ into the RTL testbench.

Compare:

```text
Python
   ↕
C++
   ↕
RTL simulation
```

Measure:

```text
coefficient mismatch
maximum error
RMS error
reconstruction error
```

Do not move to physical hardware until RTL simulation passes.

---

# C8 — Synthesize the DWT

Run Quartus synthesis.

Record:

```text
Logic utilization
Registers
Memory blocks
DSP usage
Fmax
Estimated power
Latency
Throughput
```

This is your first genuine hardware result.

---

# C9 — Program the DWT onto DE1-SoC FPGA fabric

Now:

```text
DE1-SoC FPGA
      |
      v
DWT hardware
```

Send test vectors from the ARM HPS to the FPGA.

Initially use a simple control path.

Do not optimize data movement yet.

---

# C10 — Implement the hardware Science Guardrail

Create:

```text
guardrail/
├── flux_accumulator.sv
├── x_moment_accumulator.sv
├── y_moment_accumulator.sv
├── error_calculator.sv
└── threshold_compare.sv
```

The hardware flow becomes:

```text
Pixel Stream
     |
     +----------------+
     |                |
     v                v
Flux Accumulator   X/Y Moments
     |                |
     +-------+--------+
             |
             v
       Flux/Centroid
             |
             v
       Error Calculation
             |
             v
       Threshold Compare
             |
        +----+----+
        |         |
        v         v
       SAFE      LOCK
```

---

# C11 — Verify Guardrail RTL

Compare:

```text
Python Guardrail
        ↕
C++ Guardrail
        ↕
RTL Guardrail
```

Use identical:

- pixel data,
- source locations,
- thresholds.

Verify:

```text
flux
centroid
ΔF
Δx
SAFE/LOCK decision
```

---

# C12 — Create the FPGA-to-HPS interface

The final heterogeneous system needs:

```text
ARM HPS
    |
    | AXI
    v
FPGA IP
```

Expose at minimum:

```text
CONTROL
STATUS
FRAME_ADDRESS
OUTPUT_ADDRESS
FRAME_ID
WAVELET_CONFIGURATION
EPSILON_F
EPSILON_X
```

The exact register map can be finalized during implementation.

---

# C13 — Connect bulk data transfer

After simple control communication works, implement a more efficient data path.

Target architecture:

```text
DDR Memory
    |
    | DMA
    v
FPGA DWT
    |
    v
FPGA Guardrail
    |
    v
DDR Memory
```

Use DMA for large buffers rather than software-controlled pixel-by-pixel transfers.

---

# C14 — Reconnect the FPGA accelerator to C++ EventVault

The final C++ software should not know whether DWT execution is:

```text
software
```

or:

```text
FPGA
```

The interface should conceptually remain:

```text
DWT(input)
    ↓
result
```

Then the backend changes:

```text
Phase B:
DWT() → C++

Phase C:
DWT() → FPGA
```

This keeps the higher-level EventVault software unchanged.

---

# C15 — Keep these functions on ARM initially

Do NOT immediately convert everything to RTL.

Keep:

```text
Escrow Manager
Promotion Controller
Uncertainty Estimator
Resource Controller
Telemetry
High-level Pipeline
```

on the ARM HPS.

The initial hardware/software split should be:

```text
              ARM HPS
                 |
        +--------+--------+
        |        |        |
        v        v        v
      Escrow  Scheduler  Uncertainty
        |
        v
     Telemetry

                 AXI
                  |
                  v

              FPGA FABRIC
                 |
          +------+------+
          |             |
          v             v
         DWT       Guardrail
```

---

# C16 — Hardware-in-the-loop Saved Discovery

Now run the actual EventVault-R demonstration:

```text
Synthetic / FITS frame
        |
        v
DE1-SoC ARM
        |
        v
FPGA DWT
        |
        v
FPGA Guardrail
        |
        v
ARM Escrow
        |
        v
Trigger at T25
        |
        v
Retroactive Promotion
        |
        v
Throttled Downlink
```

The system should reproduce:

```text
T10-T24 → escrow
T25      → trigger
T10-T24 → promotion
```

---

# C17 — Compare ARM-only vs ARM+FPGA

This is essential.

## Configuration A

```text
DE1-SoC ARM only
```

Measure:

```text
DWT latency
Guardrail latency
CPU utilisation
Frame throughput
Power
```

## Configuration B

```text
DE1-SoC ARM + FPGA
```

Measure the same metrics.

Create:

```text
Metric                  ARM      ARM+FPGA
--------------------------------------------
DWT latency             ____     ____
Guardrail latency       ____     ____
CPU utilisation         ____     ____
Throughput              ____     ____
Power                   ____     ____
```

The FPGA is useful only if the measured system-level results justify its complexity.

---

# C18 — Add SignalTap/debug instrumentation

Use FPGA-side debug instrumentation to observe:

- input stream,
- DWT valid signals,
- layer generation,
- FIFO occupancy,
- guardrail output,
- AXI transactions,
- timing behavior.

This makes hardware debugging practical.

---

# C19 — Stress-test the integrated system

Test:

### Memory pressure

```text
Escrow near full
```

### High source density

```text
Many detected sources
```

### Low SNR

```text
Weak transient
```

### Long observation sequence

```text
Hundreds/thousands of frames
```

### Trigger bursts

```text
Multiple promotions
```

### Communication bottleneck

```text
Severely throttled downlink
```

The system must maintain deterministic behavior.

---

# C20 — Final TRL-4 demonstration

The final demonstration should be a controlled laboratory breadboard.

It should contain:

```text
                EVENTVAULT-R
                     |
        +------------+------------+
        |                         |
        v                         v
   DE1-SoC ARM                FPGA Fabric
        |                         |
   Controller              DWT + Guardrail
        |                         |
        +------------+------------+
                     |
                 DDR Memory
                     |
                     v
             Simulated Camera
                     |
                     v
              Throttled Link
                     |
                     v
              Ground Emulator
```

The demonstrator should show:

1. Frame ingestion.
2. Progressive DWT.
3. Scientific guardrail.
4. Escrow storage.
5. Uncertainty-aware retention.
6. Resource control.
7. Trigger detection.
8. Retroactive promotion.
9. Data transmission.
10. Logged performance.

---

# Phase C definition of done

Phase C is complete when:

- DWT RTL simulates correctly.
- DWT RTL matches golden vectors.
- DWT is synthesized successfully.
- Guardrail RTL matches C++/Python.
- FPGA IP executes on DE1-SoC.
- ARM and FPGA communicate correctly.
- EventVault-R C++ uses the FPGA accelerator.
- Saved Discovery works on the integrated system.
- Timing is measured.
- Memory usage is measured.
- FPGA utilization is reported.
- ARM-only and ARM+FPGA results are compared.
- The complete pipeline is demonstrated under controlled laboratory conditions.

At that point:

> **You have a genuine integrated hardware/software EventVault-R demonstrator rather than a software simulation.**

---

# Verification hierarchy

The complete project should always maintain this chain:

```text
              PYTHON
          GOLDEN REFERENCE
                 |
          +------+------+
          |             |
          v             v
         C++           RTL
          |             |
          v             v
      ARM HPS         FPGA
          |             |
          +------+------+
                 |
                 v
           SYSTEM OUTPUT
```

Every stage is checked against its reference.

---

# Recommended milestone sequence

## Phase B

```text
B1  C++ project skeleton
B2  DWT floating-point port
B3  Golden-vector generation
B4  Python ↔ C++ verification
B5  Fixed-point DWT
B6  Fixed-point scientific validation
B7  Guardrail port
B8  Escrow port
B9  Escrow state machine
B10 Uncertainty port
B11 Resource controller port
B12 Telemetry port
B13 Complete C++ pipeline
B14 Full cross-validation
B15 C++ Saved Discovery
B16 C++ Rate-Distortion
B17 Performance profiling
B18 DE1-SoC ARM deployment
B19 DE1-SoC profiling
B20 Phase-B signoff
```

## Phase C

```text
C1  Freeze C++ interface
C2  Generate FPGA golden vectors
C3  Create Quartus project
C4  1-D DWT lifting block
C5  Line buffers
C6  2-D / 3-level DWT
C7  RTL simulation
C8  Synthesis
C9  FPGA deployment
C10 Hardware guardrail
C11 Guardrail verification
C12 ARM-FPGA interface
C13 DMA / bulk data path
C14 EventVault integration
C15 Hardware-in-the-loop Saved Discovery
C16 ARM-only vs FPGA comparison
C17 SignalTap instrumentation
C18 Stress testing
C19 Optimization
C20 TRL-4 demonstration
```

---

# Final engineering philosophy

```text
        Mathematical idea
               |
               v
        Python reference
               |
               v
       Verified C++ model
               |
               v
        Embedded execution
               |
               v
        FPGA acceleration
               |
               v
      Integrated hardware
               |
               v
             TRL-4
```

Do not skip layers.

If something fails on FPGA:

```text
FPGA output
    ↓
Compare with C++
    ↓
Compare with Python
    ↓
Determine where divergence began
```

This makes the development process much easier to debug and gives the final project a traceable verification chain.

---

# Immediate next action

**Start with B1, not C1.**

Your next practical task is:

```text
1. Create embedded/
2. Set up CMake
3. Port dwt.py → dwt.cpp
4. Create Python golden vectors
5. Compare Python vs C++
6. Do not touch Quartus yet
```

The FPGA work should begin only after the C++ implementation is stable and verified.
