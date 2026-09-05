// =============================================================================
//  dwt_1d_bior.sv — 1-D Biorthogonal 4.4 / db4 Discrete Wavelet Transform
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V (DE1-SoC)
//
//  Computes the 1-D DWT using convolution (polyphase FIR).
//  Matches the C++ Q16.16 Fixed-Point Reference.
//
//  dec_lo = [0, 2479, -1563, -7250, 24733, 55882, 24733, -7250, -1563, 2479]
//  dec_hi = [0, -4229, 2666, 27400, -51674, 27400, 2666, -4229, 0, 0]
// =============================================================================

module dwt_1d_bior #(
    parameter int Q_FRACT_W = 16,
    parameter int IN_W      = 32,
    parameter int OUT_W     = 32
)(
    input  logic             clk,
    input  logic             rst_n,

    // ---- Streaming input ------------------------------------------------
    input  logic             in_valid,
    input  logic [IN_W-1:0]  in_data,
    input  logic             in_last,
    output logic             in_ready,

    // ---- Low-pass output ------------------------------------------------
    output logic             lo_valid,
    output logic [OUT_W-1:0] lo_data,
    output logic             lo_last,

    // ---- High-pass output -----------------------------------------------
    output logic             hi_valid,
    output logic [OUT_W-1:0] hi_data,
    output logic             hi_last
);

    // Q16.16 Bior4.4 Coefficients
    localparam signed [IN_W-1:0] L0 = 0, L1 = 2479, L2 = -1563, L3 = -7250, L4 = 24733, L5 = 55882, L6 = 24733, L7 = -7250, L8 = -1563, L9 = 2479;
    localparam signed [IN_W-1:0] H0 = 0, H1 = -4229, H2 = 2666, H3 = 27400, H4 = -51674, H5 = 27400, H6 = 2666, H7 = -4229, H8 = 0, H9 = 0;

    // Shift Register (10 taps)
    logic signed [IN_W-1:0] shift_reg [0:9];
    logic                   phase; // 0 = even, 1 = odd
    
    // Multipliers (Pipeline Stage 1)
    logic signed [63:0] mult_lo [0:9];
    logic signed [63:0] mult_hi [0:9];
    logic               stg1_valid;
    logic               stg1_last;

    // Accumulators (Pipeline Stage 2)
    logic signed [63:0] sum_lo;
    logic signed [63:0] sum_hi;
    logic               stg2_valid;
    logic               stg2_last;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            phase <= 1'b0;
            stg1_valid <= 1'b0;
            stg2_valid <= 1'b0;
            lo_valid <= 1'b0;
            hi_valid <= 1'b0;
            for (int i=0; i<10; i++) shift_reg[i] <= '0;
        end else begin
            // -----------------------------------------------------------------
            // Input Stage (Shift Register)
            // -----------------------------------------------------------------
            if (in_valid) begin
                for (int i=9; i>0; i--) begin
                    shift_reg[i] <= shift_reg[i-1];
                end
                shift_reg[0] <= in_data;
                
                if (phase == 1'b1) begin
                    // Odd sample received -> Compute
                    phase <= 1'b0;
                    stg1_valid <= 1'b1;
                    stg1_last  <= in_last;
                end else begin
                    phase <= 1'b1;
                    stg1_valid <= 1'b0;
                    stg1_last  <= 1'b0;
                end
            end else begin
                stg1_valid <= 1'b0;
                stg1_last  <= 1'b0;
            end

            // -----------------------------------------------------------------
            // Pipeline Stage 1: Multiply
            // -----------------------------------------------------------------
            if (stg1_valid) begin
                // Note: Array indexing matches C++ formula: x[2k+1-j] * f[j]
                // shift_reg[0] is x[2k+1] (j=0)
                // shift_reg[9] is x[2k-8] (j=9)
                mult_lo[0] <= shift_reg[0] * L0;
                mult_lo[1] <= shift_reg[1] * L1;
                mult_lo[2] <= shift_reg[2] * L2;
                mult_lo[3] <= shift_reg[3] * L3;
                mult_lo[4] <= shift_reg[4] * L4;
                mult_lo[5] <= shift_reg[5] * L5;
                mult_lo[6] <= shift_reg[6] * L6;
                mult_lo[7] <= shift_reg[7] * L7;
                mult_lo[8] <= shift_reg[8] * L8;
                mult_lo[9] <= shift_reg[9] * L9;

                mult_hi[0] <= shift_reg[0] * H0;
                mult_hi[1] <= shift_reg[1] * H1;
                mult_hi[2] <= shift_reg[2] * H2;
                mult_hi[3] <= shift_reg[3] * H3;
                mult_hi[4] <= shift_reg[4] * H4;
                mult_hi[5] <= shift_reg[5] * H5;
                mult_hi[6] <= shift_reg[6] * H6;
                mult_hi[7] <= shift_reg[7] * H7;
                mult_hi[8] <= shift_reg[8] * H8;
                mult_hi[9] <= shift_reg[9] * H9;
            end
            stg2_valid <= stg1_valid;
            stg2_last  <= stg1_last;

            // -----------------------------------------------------------------
            // Pipeline Stage 2: Accumulate & Shift
            // -----------------------------------------------------------------
            if (stg2_valid) begin
                sum_lo <= mult_lo[0] + mult_lo[1] + mult_lo[2] + mult_lo[3] + mult_lo[4] + mult_lo[5] + mult_lo[6] + mult_lo[7] + mult_lo[8] + mult_lo[9];
                sum_hi <= mult_hi[0] + mult_hi[1] + mult_hi[2] + mult_hi[3] + mult_hi[4] + mult_hi[5] + mult_hi[6] + mult_hi[7] + mult_hi[8] + mult_hi[9];
                
                // Shift down by Q_FRACT_W (16)
                lo_data <= (mult_lo[0] + mult_lo[1] + mult_lo[2] + mult_lo[3] + mult_lo[4] + mult_lo[5] + mult_lo[6] + mult_lo[7] + mult_lo[8] + mult_lo[9]) >>> Q_FRACT_W;
                hi_data <= (mult_hi[0] + mult_hi[1] + mult_hi[2] + mult_hi[3] + mult_hi[4] + mult_hi[5] + mult_hi[6] + mult_hi[7] + mult_hi[8] + mult_hi[9]) >>> Q_FRACT_W;
            end
            lo_valid <= stg2_valid;
            hi_valid <= stg2_valid;
            lo_last  <= stg2_last;
            hi_last  <= stg2_last;
        end
    end

    assign in_ready = 1'b1;

endmodule
