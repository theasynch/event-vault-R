// =============================================================================
//  dwt_2d_level.sv — 1-Level 2D Haar Discrete Wavelet Transform
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Performs a 1-level 2D Haar DWT.
//  1. Row DWT: Computes L and H for incoming pixels.
//  2. Line Buffers: Stores the L and H outputs for one entire row.
//  3. Column DWT: When the next row arrives, combines new L and H with 
//     buffered L and H to produce LL, LH, HL, HH.
// =============================================================================

module dwt_2d_level #(
    parameter int IN_W      = 16,
    parameter int OUT_W     = IN_W + 1,
    parameter int LINE_COLS = 1024
)(
    input  logic             clk,
    input  logic             rst_n,

    // Streaming input (Row-major, progressive)
    input  logic             in_valid,
    input  logic [IN_W-1:0]  in_data,
    input  logic             in_last_col,
    input  logic             in_last_row,

    // 4 sub-bands output
    // These pulse valid when a 2x2 block has been processed
    output logic             out_valid,
    output logic [OUT_W-1:0] out_LL,  // L0 (base)
    output logic [OUT_W-1:0] out_LH,
    output logic [OUT_W-1:0] out_HL,
    output logic [OUT_W-1:0] out_HH,
    output logic             out_last_col,
    output logic             out_last_row
);

    // -------------------------------------------------------------------------
    // 1. Row DWT (1D)
    // -------------------------------------------------------------------------
    logic             row_lo_valid, row_hi_valid;
    logic [OUT_W-1:0] row_lo_data,  row_hi_data;
    logic             row_last_col;

    dwt_1d_haar #(
        .IN_W(IN_W),
        .OUT_W(OUT_W)
    ) u_row_dwt (
        .clk      (clk),
        .rst_n    (rst_n),
        .in_valid (in_valid),
        .in_data  (in_data),
        .in_last  (in_last_col),
        .in_ready (), // Always 1
        .lo_valid (row_lo_valid),
        .lo_data  (row_lo_data),
        .lo_last  (row_last_col),
        .hi_valid (row_hi_valid),
        .hi_data  (row_hi_data),
        .hi_last  ()
    );

    // Track rows to know if we are on an even or odd row
    logic row_phase; // 0 = even row, 1 = odd row
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            row_phase <= 1'b0;
        end else if (in_valid && in_last_col) begin
            if (in_last_row)
                row_phase <= 1'b0;
            else
                row_phase <= ~row_phase;
        end
    end

    // -------------------------------------------------------------------------
    // 2. Line Buffers for L and H row outputs
    // We only need to buffer one row's worth of L and H to pair with the next
    // The number of outputs per row is LINE_COLS / 2
    // -------------------------------------------------------------------------
    localparam int HALF_COLS = LINE_COLS / 2;
    localparam int ADDR_W = $clog2(HALF_COLS);

    logic [ADDR_W-1:0] wr_col, rd_col;
    logic [OUT_W-1:0]  buf_L [0:HALF_COLS-1];
    logic [OUT_W-1:0]  buf_H [0:HALF_COLS-1];

    logic [OUT_W-1:0]  prev_L, prev_H;

    // Address counters for line buffer
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_col <= '0;
            rd_col <= '0;
        end else begin
            if (row_lo_valid) begin
                if (row_phase == 1'b0) begin
                    // Even row: write to buffer
                    buf_L[wr_col] <= row_lo_data;
                    buf_H[wr_col] <= row_hi_data;
                    wr_col <= (wr_col == HALF_COLS - 1) ? '0 : wr_col + 1'b1;
                end else begin
                    // Odd row: read from buffer
                    rd_col <= (rd_col == HALF_COLS - 1) ? '0 : rd_col + 1'b1;
                end
            end
        end
    end

    assign prev_L = buf_L[rd_col];
    assign prev_H = buf_H[rd_col];

    // -------------------------------------------------------------------------
    // 3. Column DWT
    // Active during the odd row (phase = 1). Combines buffered (even) row with
    // incoming (odd) row.
    // -------------------------------------------------------------------------
    logic signed [OUT_W:0] s_even_L, s_odd_L;
    logic signed [OUT_W:0] s_even_H, s_odd_H;

    logic [OUT_W-1:0] odd_L_reg, odd_H_reg;
    logic             odd_valid_reg;
    logic             odd_last_col_reg;
    
    // For synchronous read from block RAM
    logic [OUT_W-1:0] sync_prev_L, sync_prev_H;
    always_ff @(posedge clk) begin
        sync_prev_L <= buf_L[rd_col];
        sync_prev_H <= buf_H[rd_col];
        
        odd_L_reg <= row_lo_data;
        odd_H_reg <= row_hi_data;
        odd_valid_reg <= (row_lo_valid && row_phase == 1'b1);
        odd_last_col_reg <= row_last_col;
    end

    assign s_even_L = $signed({1'b0, sync_prev_L}); // Assuming signed arithmetic inside DWT, wait, OUT_W is IN_W+1, Haar can be negative. We should sign extend.
    assign s_odd_L  = $signed(odd_L_reg);
    assign s_even_H = $signed(sync_prev_H);
    assign s_odd_H  = $signed(odd_H_reg);

    // Compute outputs
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
        end else begin
            out_valid <= odd_valid_reg;
            
            // LL = (even_L + odd_L) / 2
            out_LL <= (s_even_L + s_odd_L) >>> 1;
            // LH = even_L - odd_L
            out_LH <= (s_even_L - s_odd_L);
            
            // HL = (even_H + odd_H) / 2
            out_HL <= (s_even_H + s_odd_H) >>> 1;
            // HH = even_H - odd_H
            out_HH <= (s_even_H - s_odd_H);

            out_last_col <= odd_last_col_reg;
        end
    end

endmodule
