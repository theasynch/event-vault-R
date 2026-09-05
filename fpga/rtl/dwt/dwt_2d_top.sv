// =============================================================================
//  dwt_2d_top.sv — 3-Level 2D Bior4.4 Discrete Wavelet Transform
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Progressive 3-level decomposition.
//  Input: Stream of calibrated pixels (32-bit Q16.16)
//  Outputs: 
//    Level 1: H1 (LH1, HL1, HH1)
//    Level 2: H2 (LH2, HL2, HH2)
//    Level 3: H3 (LH3, HL3, HH3) and L0 (Base Layer = LL3)
//
//  Data format: Strictly 32-bit Q16.16 fixed-point throughout the pipeline.
// =============================================================================

module dwt_2d_top #(
    parameter int LINE_COLS = 1024
)(
    input  logic             clk,
    input  logic             rst_n,

    // Streaming input
    input  logic             in_valid,
    input  logic [31:0]      in_data,
    input  logic             in_last_col,
    input  logic             in_last_row,

    // Level 1 Residuals (H1)
    output logic             l1_valid,
    output logic [31:0]      l1_LH,
    output logic [31:0]      l1_HL,
    output logic [31:0]      l1_HH,

    // Level 2 Residuals (H2)
    output logic             l2_valid,
    output logic [31:0]      l2_LH,
    output logic [31:0]      l2_HL,
    output logic [31:0]      l2_HH,

    // Level 3 Residuals (H3) and Base (L0)
    output logic             l3_valid,
    output logic [31:0]      l3_LH,
    output logic [31:0]      l3_HL,
    output logic [31:0]      l3_HH,
    output logic [31:0]      base_L0,
    
    // Status
    output logic             done
);

    // -------------------------------------------------------------------------
    // Level 1
    // -------------------------------------------------------------------------
    logic        l1_LL_valid;
    logic [31:0] l1_LL_data;
    logic        l1_last_col, l1_last_row;

    dwt_2d_level #(
        .LINE_COLS(LINE_COLS)
    ) level_1 (
        .clk          (clk),
        .rst_n        (rst_n),
        .in_valid     (in_valid),
        .in_data      (in_data),
        .in_last_col  (in_last_col),
        .in_last_row  (in_last_row),
        .out_valid    (l1_LL_valid),
        .out_LL       (l1_LL_data),
        .out_LH       (l1_LH),
        .out_HL       (l1_HL),
        .out_HH       (l1_HH),
        .out_last_col (l1_last_col),
        .out_last_row (l1_last_row)
    );
    assign l1_valid = l1_LL_valid;

    // -------------------------------------------------------------------------
    // Level 2
    // -------------------------------------------------------------------------
    logic        l2_LL_valid;
    logic [31:0] l2_LL_data;
    logic        l2_last_col, l2_last_row;

    dwt_2d_level #(
        .LINE_COLS(LINE_COLS / 2)
    ) level_2 (
        .clk          (clk),
        .rst_n        (rst_n),
        .in_valid     (l1_LL_valid),
        .in_data      (l1_LL_data),
        .in_last_col  (l1_last_col),
        .in_last_row  (l1_last_row),
        .out_valid    (l2_LL_valid),
        .out_LL       (l2_LL_data),
        .out_LH       (l2_LH),
        .out_HL       (l2_HL),
        .out_HH       (l2_HH),
        .out_last_col (l2_last_col),
        .out_last_row (l2_last_row)
    );
    assign l2_valid = l2_LL_valid;

    // -------------------------------------------------------------------------
    // Level 3
    // -------------------------------------------------------------------------
    logic        l3_last_col, l3_last_row;

    dwt_2d_level #(
        .LINE_COLS(LINE_COLS / 4)
    ) level_3 (
        .clk          (clk),
        .rst_n        (rst_n),
        .in_valid     (l2_LL_valid),
        .in_data      (l2_LL_data),
        .in_last_col  (l2_last_col),
        .in_last_row  (l2_last_row),
        .out_valid    (l3_valid),
        .out_LL       (base_L0),
        .out_LH       (l3_LH),
        .out_HL       (l3_HL),
        .out_HH       (l3_HH),
        .out_last_col (l3_last_col),
        .out_last_row (l3_last_row)
    );

    // Frame done when Level 3 outputs its last block
    assign done = l3_valid && l3_last_row && l3_last_col;

endmodule
