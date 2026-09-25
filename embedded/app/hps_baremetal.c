// =============================================================================
//  hps_baremetal.c — Bare-Metal ARM Benchmark for EventVault-R
//
//  Runs DIRECTLY on the ARM Cortex-A9 without any OS (no Linux, no SD card).
//  Uses UART0 for serial output and the ARM Global Timer for timing.
//
//  Load via JTAG using Intel SoC EDS tools.
//
//  Cross-compile:
//    arm-none-eabi-gcc -mcpu=cortex-a9 -mfloat-abi=hard -mfpu=neon \
//      -O2 -nostdlib -Tbaremetal.ld -o hps_baremetal.elf hps_baremetal.c
// =============================================================================

// =============================================================================
// Hardware Register Addresses (Cyclone V SoC)
// =============================================================================

// UART0 (Synopsys DesignWare APB UART)
#define UART0_BASE          0xFFC02000
#define UART0_RBR           (*(volatile unsigned int *)(UART0_BASE + 0x00)) // RX
#define UART0_THR           (*(volatile unsigned int *)(UART0_BASE + 0x00)) // TX
#define UART0_IER           (*(volatile unsigned int *)(UART0_BASE + 0x04))
#define UART0_FCR           (*(volatile unsigned int *)(UART0_BASE + 0x08))
#define UART0_LCR           (*(volatile unsigned int *)(UART0_BASE + 0x0C))
#define UART0_MCR           (*(volatile unsigned int *)(UART0_BASE + 0x10))
#define UART0_LSR           (*(volatile unsigned int *)(UART0_BASE + 0x14))
#define UART0_DLL           (*(volatile unsigned int *)(UART0_BASE + 0x00))
#define UART0_DLH           (*(volatile unsigned int *)(UART0_BASE + 0x04))

// UART LSR bits
#define UART_LSR_THRE       0x20  // Transmit Holding Register Empty
#define UART_LSR_DR         0x01  // Data Ready

// ARM Cortex-A9 Global Timer (runs at half MPU clock = 400 MHz on DE1-SoC)
#define GLOBAL_TIMER_BASE   0xFFFEC200
#define GT_COUNTER_LO       (*(volatile unsigned int *)(GLOBAL_TIMER_BASE + 0x00))
#define GT_COUNTER_HI       (*(volatile unsigned int *)(GLOBAL_TIMER_BASE + 0x04))
#define GT_CONTROL          (*(volatile unsigned int *)(GLOBAL_TIMER_BASE + 0x08))

#define GT_FREQ             400000000ULL  // 400 MHz (MPU 800 MHz / 2)

// Lightweight HPS-to-FPGA Bridge
#define LW_BRIDGE_BASE      0xFF200000

// EventVault-R Register Map (matching evaultr_top.sv)
// Write registers
#define ACCEL_CONTROL       (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x00))
#define ACCEL_PIXEL         (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x04))
#define ACCEL_FRAME_ID      (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x08))
#define ACCEL_EPS_F         (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x0C))
#define ACCEL_EPS_X         (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x10))
#define ACCEL_LAST_FLAGS    (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x14))

// Read registers
#define ACCEL_STATUS        (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x00))
#define ACCEL_RESULT        (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x04))
#define ACCEL_PERF_CNT      (*(volatile unsigned int *)(LW_BRIDGE_BASE + 0x08))

// =============================================================================
// Q16.16 Fixed-Point
// =============================================================================
typedef int q16_t;
#define Q16_SHIFT  16
#define FLOAT_TO_Q16(f)  ((q16_t)((f) * (1 << Q16_SHIFT)))
#define Q16_MUL(a, b)    ((q16_t)(((long long)(a) * (long long)(b)) >> Q16_SHIFT))

// Frame size
#define ROWS  64
#define COLS  64
#define NUM_PIXELS (ROWS * COLS)

// =============================================================================
// UART Functions (Bare-Metal Output)
// =============================================================================

static void uart_init(void) {
    // The preloader/U-Boot usually initializes UART0 already.
    // But let's set it up just in case.
    //
    // UART clock on DE1-SoC = 100 MHz (l4_sp_clk)
    // For 115200 baud: divisor = 100000000 / (16 * 115200) = 54

    UART0_LCR = 0x83;      // DLAB=1, 8N1
    UART0_DLL = 54;         // Divisor low byte
    UART0_DLH = 0;          // Divisor high byte
    UART0_LCR = 0x03;       // DLAB=0, 8N1
    UART0_FCR = 0x07;       // Enable and reset FIFOs
    UART0_IER = 0x00;       // No interrupts
    UART0_MCR = 0x03;       // RTS + DTR
}

static void uart_putc(char c) {
    while (!(UART0_LSR & UART_LSR_THRE))
        ;  // Wait for TX buffer empty
    UART0_THR = c;
}

static void uart_puts(const char *s) {
    while (*s) {
        if (*s == '\n')
            uart_putc('\r');
        uart_putc(*s++);
    }
}

// Simple integer to string (no stdlib)
static void uart_print_uint(unsigned int val) {
    char buf[12];
    int i = 0;
    if (val == 0) {
        uart_putc('0');
        return;
    }
    while (val > 0) {
        buf[i++] = '0' + (val % 10);
        val /= 10;
    }
    while (i > 0)
        uart_putc(buf[--i]);
}

static void uart_print_hex(unsigned int val) {
    const char hex[] = "0123456789ABCDEF";
    uart_puts("0x");
    for (int i = 28; i >= 0; i -= 4)
        uart_putc(hex[(val >> i) & 0xF]);
}

// Print a fixed-point decimal (3 decimal places)
static void uart_print_fixed(unsigned long long microseconds) {
    unsigned int ms_whole = (unsigned int)(microseconds / 1000);
    unsigned int ms_frac  = (unsigned int)(microseconds % 1000);
    uart_print_uint(ms_whole);
    uart_putc('.');
    if (ms_frac < 100) uart_putc('0');
    if (ms_frac < 10)  uart_putc('0');
    uart_print_uint(ms_frac);
}

// =============================================================================
// Global Timer Functions
// =============================================================================

static void timer_init(void) {
    // Enable global timer
    GT_CONTROL = 0x01;  // Enable, no auto-increment, no interrupt
}

static unsigned long long timer_read(void) {
    unsigned int hi, lo, hi2;
    // Must read hi-lo-hi to handle rollover
    do {
        hi  = GT_COUNTER_HI;
        lo  = GT_COUNTER_LO;
        hi2 = GT_COUNTER_HI;
    } while (hi != hi2);
    return ((unsigned long long)hi << 32) | lo;
}

// Convert timer ticks to microseconds
static unsigned long long ticks_to_us(unsigned long long ticks) {
    return (ticks * 1000000ULL) / GT_FREQ;
}

// =============================================================================
// Bior4.4 Filter Coefficients (Q16.16)
// =============================================================================

// Pre-computed Q16.16 values of the bior4.4 decomposition low-pass filter (9 taps)
static const q16_t bior44_lo[9] = {
    0,          // 0.0
    -4228,      // -0.06453888
    2666,       //  0.04068942
    27396,      //  0.41809227
    -51672,     // -0.78848562
    27396,      //  0.41809227
    2666,       //  0.04068942
    -4228,      // -0.06453888
    0           //  0.0
};

static const q16_t bior44_hi[7] = {
    0,          // 0.0
    2479,       //  0.03782846
    -1563,      // -0.02384947
    -7247,      // -0.11062440
    24731,      //  0.37740286
    -55873,     // -0.85269868
    24731       //  0.37740286
};

// =============================================================================
// Software DWT (runs entirely on ARM)
// =============================================================================

static q16_t sw_buf_L[NUM_PIXELS];
static q16_t sw_buf_H[NUM_PIXELS];
static q16_t sw_col[ROWS];
static q16_t sw_lo[ROWS];
static q16_t sw_hi[ROWS];

// Symmetric boundary extension
static int mirror(int idx, int len) {
    if (idx < 0) idx = -idx;
    if (idx >= len) idx = 2 * (len - 1) - idx;
    if (idx < 0) idx = 0;
    if (idx >= len) idx = len - 1;
    return idx;
}

static void dwt_1d(const q16_t *in, int len, q16_t *lo, q16_t *hi) {
    int out_len = (len + 1) / 2;
    for (int n = 0; n < out_len; n++) {
        long long acc_lo = 0, acc_hi = 0;
        for (int k = 0; k < 9; k++) {
            int idx = mirror(2 * n - 4 + k, len);
            acc_lo += (long long)in[idx] * (long long)bior44_lo[k];
        }
        lo[n] = (q16_t)(acc_lo >> Q16_SHIFT);

        for (int k = 0; k < 7; k++) {
            int idx = mirror(2 * n - 3 + k, len);
            acc_hi += (long long)in[idx] * (long long)bior44_hi[k];
        }
        hi[n] = (q16_t)(acc_hi >> Q16_SHIFT);
    }
}

static void dwt_2d_sw(const q16_t *in, int rows, int cols) {
    int hc = (cols + 1) / 2;
    int hr = (rows + 1) / 2;

    // Row transform
    for (int r = 0; r < rows; r++)
        dwt_1d(&in[r * cols], cols, &sw_buf_L[r * hc], &sw_buf_H[r * hc]);

    // Column transform on L
    for (int c = 0; c < hc; c++) {
        for (int r = 0; r < rows; r++)
            sw_col[r] = sw_buf_L[r * hc + c];
        dwt_1d(sw_col, rows, sw_lo, sw_hi);
        // LL and LH stored back (we don't need to keep them, just compute)
        (void)sw_lo; (void)sw_hi;
    }

    // Column transform on H
    for (int c = 0; c < hc; c++) {
        for (int r = 0; r < rows; r++)
            sw_col[r] = sw_buf_H[r * hc + c];
        dwt_1d(sw_col, rows, sw_lo, sw_hi);
        (void)sw_lo; (void)sw_hi;
    }
}

// 3-level DWT
static void dwt_3level_sw(const q16_t *frame) {
    // Level 1: 64x64 → 32x32
    dwt_2d_sw(frame, 64, 64);
    // Level 2: 32x32 → 16x16 (operate on LL from level 1)
    // For timing purposes, we just run the same computation 3 times
    // at decreasing sizes to approximate the real workload
    dwt_2d_sw(frame, 32, 32);
    // Level 3: 16x16 → 8x8
    dwt_2d_sw(frame, 16, 16);
}

// =============================================================================
// Test Frame Buffer (static allocation — no malloc in bare-metal)
// =============================================================================
static q16_t test_frame[NUM_PIXELS];

// Simple pseudo-random number generator (no stdlib)
static unsigned int rand_state = 42;
static unsigned int simple_rand(void) {
    rand_state = rand_state * 1103515245 + 12345;
    return (rand_state >> 16) & 0x7FFF;
}

// =============================================================================
// Main Entry Point
// =============================================================================

void main(void) {
    uart_init();
    timer_init();

    uart_puts("\n\n");
    uart_puts("==================================================\n");
    uart_puts(" EventVault-R Bare-Metal HPS-FPGA Benchmark\n");
    uart_puts(" Platform: DE1-SoC (Cyclone V, ARM Cortex-A9)\n");
    uart_puts(" Mode: Bare-Metal (No OS, No SD Card)\n");
    uart_puts(" Frame Size: 64 x 64 pixels\n");
    uart_puts("==================================================\n\n");

    // Generate synthetic test frame
    uart_puts("Generating test frame...\n");
    for (int r = 0; r < ROWS; r++) {
        for (int c = 0; c < COLS; c++) {
            // Simple gradient + noise pattern
            int val = 100 + (r * 50 / ROWS) + (c * 30 / COLS) + (simple_rand() % 10);
            test_frame[r * COLS + c] = FLOAT_TO_Q16(val);
        }
    }

    // =================================================================
    // EXPERIMENT 1: Software-only DWT on ARM
    // =================================================================
    uart_puts("[1] Software DWT (ARM Cortex-A9, 800 MHz)\n");

    int num_iterations = 100;
    unsigned long long t_start = timer_read();

    for (int i = 0; i < num_iterations; i++) {
        dwt_3level_sw(test_frame);
    }

    unsigned long long t_end = timer_read();
    unsigned long long total_us = ticks_to_us(t_end - t_start);
    unsigned long long per_frame_us = total_us / num_iterations;

    uart_puts("  Iterations: ");
    uart_print_uint(num_iterations);
    uart_puts("\n");

    uart_puts("  Total Time: ");
    uart_print_fixed(total_us);
    uart_puts(" ms\n");

    uart_puts("  Per Frame:  ");
    uart_print_fixed(per_frame_us);
    uart_puts(" ms\n");

    unsigned int sw_fps = 0;
    if (per_frame_us > 0)
        sw_fps = (unsigned int)(1000000ULL / per_frame_us);
    uart_puts("  Frame Rate: ");
    uart_print_uint(sw_fps);
    uart_puts(" FPS\n\n");

    // =================================================================
    // EXPERIMENT 2: Hardware DWT via FPGA
    // =================================================================
    uart_puts("[2] Hardware DWT (FPGA via Lightweight Bridge)\n");

    // Read FPGA performance counter before streaming
    unsigned int fpga_cyc_start = ACCEL_PERF_CNT;

    // Stream all pixels into the FPGA
    for (int r = 0; r < ROWS; r++) {
        for (int c = 0; c < COLS; c++) {
            // Set last flags
            unsigned int flags = 0;
            if (c == COLS - 1) flags |= 0x1;  // last_col
            if (r == ROWS - 1 && c == COLS - 1) flags |= 0x2;  // last_row
            ACCEL_LAST_FLAGS = flags;

            // Write pixel (triggers DWT pipeline)
            ACCEL_PIXEL = (unsigned int)test_frame[r * COLS + c];
        }
    }

    // Wait for completion
    int timeout = 1000000;
    while (!(ACCEL_STATUS & 0x1) && timeout > 0)
        timeout--;

    unsigned int fpga_cyc_end = ACCEL_PERF_CNT;
    unsigned int hw_cycles = fpga_cyc_end - fpga_cyc_start;

    // FPGA runs at 50 MHz, so each cycle = 20 ns = 0.02 us
    unsigned long long hw_us = (unsigned long long)hw_cycles * 20ULL / 1000ULL; // in microseconds

    uart_puts("  FPGA Cycles:     ");
    uart_print_uint(hw_cycles);
    uart_puts("\n");

    uart_puts("  Per Frame:       ");
    uart_print_fixed(hw_us);
    uart_puts(" ms\n");

    unsigned int hw_fps = 0;
    if (hw_us > 0)
        hw_fps = (unsigned int)(1000000ULL / hw_us);
    uart_puts("  Frame Rate:      ");
    uart_print_uint(hw_fps);
    uart_puts(" FPS\n");

    // Read results
    unsigned int last_l0 = ACCEL_RESULT;
    unsigned int status  = ACCEL_STATUS;

    uart_puts("  Last L0 Value:   ");
    uart_print_hex(last_l0);
    uart_puts("\n");

    uart_puts("  Guardrail Safe:  ");
    uart_puts((status & 0x4) ? "YES" : "NO");
    uart_puts("\n");

    if (timeout <= 0)
        uart_puts("  WARNING: FPGA timed out!\n");

    uart_puts("\n");

    // =================================================================
    // RESULTS SUMMARY
    // =================================================================
    uart_puts("==================================================\n");
    uart_puts(" RESULTS SUMMARY\n");
    uart_puts("==================================================\n");

    uart_puts("  ARM Software:     ");
    uart_print_fixed(per_frame_us);
    uart_puts(" ms/frame  (");
    uart_print_uint(sw_fps);
    uart_puts(" FPS)\n");

    uart_puts("  FPGA Hardware:    ");
    uart_print_fixed(hw_us);
    uart_puts(" ms/frame  (");
    uart_print_uint(hw_fps);
    uart_puts(" FPS)\n");

    if (hw_us > 0 && per_frame_us > 0) {
        unsigned int speedup = (unsigned int)(per_frame_us / hw_us);
        uart_puts("  Speedup Factor:   ");
        uart_print_uint(speedup);
        uart_puts("x\n");
    }

    uart_puts("==================================================\n");
    uart_puts("\nBenchmark complete. You may now screenshot this.\n");

    // Halt
    while (1)
        ;
}

// =============================================================================
// Startup Code (minimal — ARM reset vector)
// =============================================================================
void _start(void) __attribute__((naked, section(".text.startup")));
void _start(void) {
    // Set up stack pointer (use on-chip RAM at 0xFFFF0000, 64KB)
    __asm__ volatile (
        "ldr sp, =0xFFFF0000 + 0x10000\n"  // Top of on-chip RAM
        "bl main\n"
        "b .\n"                              // Infinite loop
    );
}
