// =============================================================================
//  dwt_1d_haar.sv — 1-D Haar Discrete Wavelet Transform
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V (DE1-SoC)
//
//  Implements the 1-D Haar DWT on a streaming pixel row:
//
//    Lo[n] = (x[2n] + x[2n+1]) >> 1        (low-pass, averaging)
//    Hi[n] = (x[2n] - x[2n+1])             (high-pass, differencing)
//
//  NOTE: Haar is the default wavelet used in this RTL prototype.
//        The bior4.4 extension requires replacing this module with a
//        9-tap FIR version (bior4.4 coefficients in Q1.15) and a
//        deeper pipeline; the surrounding system remains identical.
//
//  Streaming: accepts one pixel per cycle.
//  On every pair of input pixels, it emits one Lo and one Hi sample.
//  lo_valid and hi_valid pulse together every 2 input valid cycles.
//
//  Resources: ~50 ALMs, 0 M10K, 1 DSP (adder only, no multipliers)
// =============================================================================

module dwt_1d_haar #(
    parameter int IN_W  = 16,             // input pixel width
    parameter int OUT_W = IN_W + 1        // output width (1 extra bit for diff)
)(
    input  logic             clk,
    input  logic             rst_n,

    // ---- Streaming input ------------------------------------------------
    input  logic             in_valid,
    input  logic [IN_W-1:0]  in_data,
    input  logic             in_last,     // last pixel of the input row
    output logic             in_ready,    // always 1 (single-cycle acceptance)

    // ---- Low-pass output (Lo: sum >> 1) ---------------------------------
    output logic             lo_valid,
    output logic [OUT_W-1:0] lo_data,
    output logic             lo_last,     // last Lo sample of this row

    // ---- High-pass output (Hi: difference) ------------------------------
    output logic             hi_valid,
    output logic [OUT_W-1:0] hi_data,
    output logic             hi_last      // last Hi sample of this row
);

    // -------------------------------------------------------------------------
    //  Alternate-pixel state machine
    //  phase=0 → store even pixel (x[2n])
    //  phase=1 → compute Lo and Hi using stored even + new odd pixel (x[2n+1])
    // -------------------------------------------------------------------------
    logic                phase;       // 0 = waiting for even pixel, 1 = odd
    logic [IN_W-1:0]     even_pixel;  // buffered even pixel
    logic                even_last;   // last flag of the even pixel

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase      <= 1'b0;
            even_pixel <= '0;
            even_last  <= 1'b0;
        end else if (in_valid) begin
            if (phase == 1'b0) begin
                // Capture even pixel
                even_pixel <= in_data;
                even_last  <= in_last;
                phase      <= 1'b1;
            end else begin
                // Odd pixel received — compute outputs next cycle
                phase <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    //  Combinatorial computation (registered one cycle later via output regs)
    //  Signed arithmetic: extend to IN_W+1 bits, preserve sign for Hi
    // -------------------------------------------------------------------------
    logic signed [IN_W:0]  s_even, s_odd;

    assign s_even = $signed({1'b0, even_pixel});
    assign s_odd  = $signed({1'b0, in_data});

    // Lo = (even + odd) >> 1  →  no overflow with IN_W+1 bits
    logic signed [IN_W:0]  lo_comb;
    logic signed [IN_W:0]  hi_comb;

    assign lo_comb = (s_even + s_odd) >>> 1;
    assign hi_comb =  s_even - s_odd;           // full range: -(2^IN_W-1)..+(2^IN_W-1)

    // -------------------------------------------------------------------------
    //  Output registers
    // -------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lo_valid <= 1'b0;
            hi_valid <= 1'b0;
        end else begin
            // Emit when we just consumed the odd pixel (phase was 1, now goes 0)
            if (in_valid && phase == 1'b1) begin
                lo_data  <= lo_comb[OUT_W-1:0];
                lo_last  <= in_last;           // last sample = when odd pixel is last
                lo_valid <= 1'b1;

                hi_data  <= hi_comb[OUT_W-1:0];
                hi_last  <= in_last;
                hi_valid <= 1'b1;
            end else begin
                lo_valid <= 1'b0;
                hi_valid <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    //  Always ready — single-cycle buffering of even pixel handles back-pressure
    // -------------------------------------------------------------------------
    assign in_ready = 1'b1;

endmodule
