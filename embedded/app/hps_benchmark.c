// =============================================================================
//  hps_benchmark.c — ARM HPS Benchmark for EventVault-R
//  
//  Runs on the DE1-SoC ARM Cortex-A9 under Linux.
//  Performs two timed experiments:
//    1. Software-only 3-level 2D bior4.4 DWT (on ARM)
//    2. Hardware-accelerated DWT (streaming pixels to FPGA via LW bridge)
//
//  Compile with:
//    arm-linux-gnueabihf-gcc -O2 -o hps_benchmark hps_benchmark.c -lm
//
//  Run on DE1-SoC:
//    ./hps_benchmark
// =============================================================================

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

// =============================================================================
// DE1-SoC Memory Map Constants
// =============================================================================
// The Lightweight HPS-to-FPGA bridge is mapped at physical address 0xFF200000.
// Our evaultr_top registers are at the base of this bridge.
#define LW_BRIDGE_BASE  0xFF200000
#define LW_BRIDGE_SPAN  0x00001000   // 4 KB window

// Register offsets (matching evaultr_top.sv register map)
// Write registers
#define REG_CONTROL     0x00    // bit[0] = start
#define REG_PIXEL       0x04    // Write pixel data here
#define REG_FRAME_ID    0x08    // Current frame ID
#define REG_EPS_F       0x0C    // Epsilon flux (Q15)
#define REG_EPS_X       0x10    // Epsilon centroid (Q15)
#define REG_LAST_FLAGS  0x14    // bit[0] = last_col, bit[1] = last_row

// Read registers
#define REG_STATUS      0x00    // bit[0]=done, bit[1]=ready, bit[2]=safe
#define REG_RESULT      0x04    // Last L0 output
#define REG_PERF_CNT    0x08    // Free-running cycle counter (50 MHz)

// =============================================================================
// Q16.16 Fixed-Point Helpers
// =============================================================================
typedef int32_t q16_t;
#define Q16_SHIFT  16
#define FLOAT_TO_Q16(f)  ((q16_t)((f) * (1 << Q16_SHIFT)))
#define Q16_MUL(a, b)    ((q16_t)(((int64_t)(a) * (int64_t)(b)) >> Q16_SHIFT))

// =============================================================================
// Bior4.4 Filter Coefficients (Decomposition Low-Pass, 9 taps)
// =============================================================================
static const double bior44_lo_d[9] = {
    0.0,
   -0.06453888262869706,
    0.04068941760916406,
    0.41809227322161724,
   -0.7884856164055829,
    0.41809227322161724,
    0.04068941760916406,
   -0.06453888262869706,
    0.0
};

static const double bior44_hi_d[7] = {
    0.0,
    0.03782845550726404,
   -0.02384946501955986,
   -0.11062440441843718,
    0.37740285561283066,
   -0.85269867900889385,
    0.37740285561283066
};

// Pre-scaled Q16.16 filter taps
static q16_t bior44_lo_q16[9];
static q16_t bior44_hi_q16[7];

// =============================================================================
// Test Parameters
// =============================================================================
#define ROWS  64
#define COLS  64
#define NUM_PIXELS (ROWS * COLS)

// =============================================================================
// Software DWT Implementation (runs entirely on ARM)
// =============================================================================

// Simple 1D DWT row transform (software baseline)
static void dwt_1d_row_sw(const q16_t *in, int len, q16_t *lo, q16_t *hi) {
    int out_len = (len + 1) / 2;  // Approximation for bior4.4

    for (int n = 0; n < out_len; n++) {
        int64_t acc_lo = 0, acc_hi = 0;
        for (int k = 0; k < 9; k++) {
            int idx = 2 * n - 4 + k;
            // Symmetric boundary extension
            if (idx < 0) idx = -idx;
            if (idx >= len) idx = 2 * (len - 1) - idx;
            if (idx < 0) idx = 0;
            if (idx >= len) idx = len - 1;
            acc_lo += (int64_t)in[idx] * (int64_t)bior44_lo_q16[k];
        }
        lo[n] = (q16_t)(acc_lo >> Q16_SHIFT);

        for (int k = 0; k < 7; k++) {
            int idx = 2 * n - 3 + k;
            if (idx < 0) idx = -idx;
            if (idx >= len) idx = 2 * (len - 1) - idx;
            if (idx < 0) idx = 0;
            if (idx >= len) idx = len - 1;
            acc_hi += (int64_t)in[idx] * (int64_t)bior44_hi_q16[k];
        }
        hi[n] = (q16_t)(acc_hi >> Q16_SHIFT);
    }
}

// Full 2D single-level DWT (software)
static void dwt_2d_level_sw(const q16_t *in, int rows, int cols,
                             q16_t *LL, q16_t *LH, q16_t *HL, q16_t *HH,
                             int *out_rows, int *out_cols) {
    int half_cols = (cols + 1) / 2;
    int half_rows = (rows + 1) / 2;
    *out_rows = half_rows;
    *out_cols = half_cols;

    // Temporary buffers for row transform results
    q16_t *L_rows = (q16_t *)malloc(rows * half_cols * sizeof(q16_t));
    q16_t *H_rows = (q16_t *)malloc(rows * half_cols * sizeof(q16_t));

    // Step 1: Row-wise transform
    for (int r = 0; r < rows; r++) {
        dwt_1d_row_sw(&in[r * cols], cols,
                       &L_rows[r * half_cols],
                       &H_rows[r * half_cols]);
    }

    // Step 2: Column-wise transform on L_rows -> LL, LH
    q16_t *col_buf = (q16_t *)malloc(rows * sizeof(q16_t));
    q16_t *lo_buf  = (q16_t *)malloc(half_rows * sizeof(q16_t));
    q16_t *hi_buf  = (q16_t *)malloc(half_rows * sizeof(q16_t));

    for (int c = 0; c < half_cols; c++) {
        // Extract column from L_rows
        for (int r = 0; r < rows; r++)
            col_buf[r] = L_rows[r * half_cols + c];

        dwt_1d_row_sw(col_buf, rows, lo_buf, hi_buf);

        for (int r = 0; r < half_rows; r++) {
            LL[r * half_cols + c] = lo_buf[r];
            LH[r * half_cols + c] = hi_buf[r];
        }
    }

    // Step 3: Column-wise transform on H_rows -> HL, HH
    for (int c = 0; c < half_cols; c++) {
        for (int r = 0; r < rows; r++)
            col_buf[r] = H_rows[r * half_cols + c];

        dwt_1d_row_sw(col_buf, rows, lo_buf, hi_buf);

        for (int r = 0; r < half_rows; r++) {
            HL[r * half_cols + c] = lo_buf[r];
            HH[r * half_cols + c] = hi_buf[r];
        }
    }

    free(L_rows);
    free(H_rows);
    free(col_buf);
    free(lo_buf);
    free(hi_buf);
}

// Full 3-level DWT (software baseline)
static void dwt_3level_sw(const q16_t *frame, int rows, int cols) {
    int r1, c1, r2, c2, r3, c3;
    int max_dim = rows > cols ? rows : cols;
    q16_t *LL1 = (q16_t *)malloc(max_dim * max_dim * sizeof(q16_t));
    q16_t *LH  = (q16_t *)malloc(max_dim * max_dim * sizeof(q16_t));
    q16_t *HL  = (q16_t *)malloc(max_dim * max_dim * sizeof(q16_t));
    q16_t *HH  = (q16_t *)malloc(max_dim * max_dim * sizeof(q16_t));
    q16_t *LL2 = (q16_t *)malloc(max_dim * max_dim * sizeof(q16_t));
    q16_t *LL3 = (q16_t *)malloc(max_dim * max_dim * sizeof(q16_t));

    // Level 1
    dwt_2d_level_sw(frame, rows, cols, LL1, LH, HL, HH, &r1, &c1);
    // Level 2
    dwt_2d_level_sw(LL1, r1, c1, LL2, LH, HL, HH, &r2, &c2);
    // Level 3
    dwt_2d_level_sw(LL2, r2, c2, LL3, LH, HL, HH, &r3, &c3);

    // LL3 is the final L0 base layer
    printf("  SW DWT: L0 size = %d x %d\n", r3, c3);

    free(LL1); free(LH); free(HL); free(HH);
    free(LL2); free(LL3);
}

// =============================================================================
// Timing Helper
// =============================================================================
static double get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

// =============================================================================
// Main Benchmark
// =============================================================================
int main(void) {
    printf("==================================================\n");
    printf(" EventVault-R HPS-FPGA Benchmark\n");
    printf(" Platform: DE1-SoC (Cyclone V, ARM Cortex-A9)\n");
    printf(" Frame Size: %d x %d pixels\n", ROWS, COLS);
    printf("==================================================\n\n");

    // Initialize Q16.16 filter coefficients
    for (int i = 0; i < 9; i++)
        bior44_lo_q16[i] = FLOAT_TO_Q16(bior44_lo_d[i]);
    for (int i = 0; i < 7; i++)
        bior44_hi_q16[i] = FLOAT_TO_Q16(bior44_hi_d[i]);

    // Generate a synthetic test frame (gradient + noise)
    q16_t *frame = (q16_t *)malloc(NUM_PIXELS * sizeof(q16_t));
    srand(42);
    for (int r = 0; r < ROWS; r++) {
        for (int c = 0; c < COLS; c++) {
            double val = 100.0 + 50.0 * sin(2.0 * M_PI * r / ROWS)
                                + 30.0 * cos(2.0 * M_PI * c / COLS)
                                + (rand() % 10);
            frame[r * COLS + c] = FLOAT_TO_Q16(val);
        }
    }

    // =====================================================================
    // EXPERIMENT 1: Software-only DWT on ARM
    // =====================================================================
    printf("[1] Software DWT (ARM Cortex-A9)\n");
    int num_iterations = 100;
    double t_start = get_time_ms();
    for (int i = 0; i < num_iterations; i++) {
        dwt_3level_sw(frame, ROWS, COLS);
    }
    double t_end = get_time_ms();
    double sw_time_per_frame = (t_end - t_start) / num_iterations;
    double sw_fps = 1000.0 / sw_time_per_frame;
    double sw_throughput = (ROWS * COLS * sw_fps) / 1e6;

    printf("  Iterations: %d\n", num_iterations);
    printf("  Total Time: %.2f ms\n", t_end - t_start);
    printf("  Per Frame:  %.3f ms\n", sw_time_per_frame);
    printf("  Frame Rate: %.1f FPS\n", sw_fps);
    printf("  Throughput: %.3f Megapixels/sec\n\n", sw_throughput);

    // =====================================================================
    // EXPERIMENT 2: Hardware DWT via FPGA fabric
    // =====================================================================
    printf("[2] Hardware DWT (FPGA via Lightweight Bridge)\n");

    // Open /dev/mem to access the physical address space
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("  ERROR: Could not open /dev/mem. Run as root (sudo).");
        printf("  Skipping FPGA benchmark.\n\n");
        goto results;
    }

    // Memory-map the Lightweight HPS-to-FPGA bridge
    volatile uint32_t *lw_bridge = (volatile uint32_t *)mmap(
        NULL, LW_BRIDGE_SPAN, PROT_READ | PROT_WRITE, MAP_SHARED,
        fd, LW_BRIDGE_BASE
    );
    if (lw_bridge == MAP_FAILED) {
        perror("  ERROR: mmap failed");
        close(fd);
        goto results;
    }

    // Convenience macros for register access
    #define WR_REG(offset, val)  (lw_bridge[(offset)/4] = (val))
    #define RD_REG(offset)       (lw_bridge[(offset)/4])

    // Read the starting cycle count
    uint32_t cyc_start = RD_REG(REG_PERF_CNT);

    // Stream all pixels into the FPGA, one per register write
    for (int r = 0; r < ROWS; r++) {
        for (int c = 0; c < COLS; c++) {
            // Set last_col and last_row flags BEFORE writing the pixel
            uint32_t flags = 0;
            if (c == COLS - 1) flags |= 0x1;  // last_col
            if (r == ROWS - 1 && c == COLS - 1) flags |= 0x2;  // last_row
            WR_REG(REG_LAST_FLAGS, flags);

            // Write the pixel (this triggers the DWT pipeline)
            WR_REG(REG_PIXEL, (uint32_t)frame[r * COLS + c]);
        }
    }

    // Poll for DWT completion (bit 0 of status register)
    int timeout = 1000000;
    while (!(RD_REG(REG_STATUS) & 0x1) && timeout > 0) {
        timeout--;
    }

    uint32_t cyc_end = RD_REG(REG_PERF_CNT);
    uint32_t hw_cycles = cyc_end - cyc_start;
    double hw_time_ms = (double)hw_cycles / 50000.0; // 50 MHz clock
    double hw_fps = 1000.0 / hw_time_ms;
    double hw_throughput = (ROWS * COLS * hw_fps) / 1e6;

    // Read back the last L0 result and guardrail status
    uint32_t last_l0 = RD_REG(REG_RESULT);
    uint32_t status  = RD_REG(REG_STATUS);
    int guardrail_safe = (status >> 2) & 0x1;

    printf("  FPGA Cycles:     %u\n", hw_cycles);
    printf("  Per Frame:       %.3f ms\n", hw_time_ms);
    printf("  Frame Rate:      %.1f FPS\n", hw_fps);
    printf("  Throughput:      %.3f Megapixels/sec\n", hw_throughput);
    printf("  Last L0 Value:   0x%08X\n", last_l0);
    printf("  Guardrail Safe:  %s\n\n", guardrail_safe ? "YES" : "NO");

    munmap((void *)lw_bridge, LW_BRIDGE_SPAN);
    close(fd);

    // =====================================================================
    // RESULTS SUMMARY
    // =====================================================================
results:
    printf("==================================================\n");
    printf(" RESULTS SUMMARY\n");
    printf("==================================================\n");
    printf("  ARM Software:     %.3f ms/frame  (%.1f FPS)\n", sw_time_per_frame, sw_fps);
    if (fd >= 0) {
        printf("  FPGA Hardware:    %.3f ms/frame  (%.1f FPS)\n", hw_time_ms, hw_fps);
        double speedup = sw_time_per_frame / hw_time_ms;
        printf("  Speedup Factor:   %.1fx\n", speedup);
        printf("  SW Throughput:    %.3f MP/s\n", sw_throughput);
        printf("  HW Throughput:    %.3f MP/s\n", hw_throughput);
    }
    printf("==================================================\n");

    free(frame);
    return 0;
}
