// =============================================================================
//  dwt_2d_level.sv — 1-Level 2D Bior4.4 Discrete Wavelet Transform
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Performs a 1-level 2D DWT.
//  1. Row DWT: Computes L and H for incoming pixels.
//  2. Line Buffers: Stores the L and H outputs for one entire row.
//  3. Column DWT: When the next row arrives, computes the column DWT using L and H
//     to produce LL, LH, HL, HH.
//
//  Data format: Strictly 32-bit Q16.16 fixed-point throughout the pipeline.
// =============================================================================

module dwt_2d_level #(
    parameter int LINE_COLS = 1024
)(
    input  logic             clk,
    input  logic             rst_n,

    // Streaming input (Row-major, progressive)
    input  logic             in_valid,
    input  logic [31:0]      in_data,
    input  logic             in_last_col,
    input  logic             in_last_row,

    // 4 sub-bands output
    // These pulse valid when a 2x2 block has been processed
    output logic             out_valid,
    output logic [31:0]      out_LL,  // L0 (base)
    output logic [31:0]      out_LH,
    output logic [31:0]      out_HL,
    output logic [31:0]      out_HH,
    output logic             out_last_col,
    output logic             out_last_row
);

    // -------------------------------------------------------------------------
    // 1. Row DWT (1D)
    // -------------------------------------------------------------------------
    logic        row_lo_valid, row_hi_valid;
    logic [31:0] row_lo_data,  row_hi_data;
    logic        row_last_col;

    dwt_1d_bior #(
        .Q_FRACT_W(16),
        .IN_W(32),
        .OUT_W(32)
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

    // Track rows to know if we are on an even or odd row, synchronized to OUTPUT
    logic row_phase; // 0 = even row, 1 = odd row
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            row_phase <= 1'b0;
        end else if (row_lo_valid && row_last_col) begin
            // We can't rely on in_last_row here because it's not synchronized to the output pipeline.
            // We will just toggle row_phase every row.
            row_phase <= ~row_phase;
        end
    end

    // -------------------------------------------------------------------------
    // 2. Line Buffers for L and H row outputs
    // -------------------------------------------------------------------------
    localparam int HALF_COLS = LINE_COLS / 2;
    localparam int ADDR_W = (HALF_COLS > 1) ? $clog2(HALF_COLS) : 1;

    logic [ADDR_W-1:0] wr_col, rd_col;
    logic [31:0]       buf_L [0:HALF_COLS-1];
    logic [31:0]       buf_H [0:HALF_COLS-1];

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

    // -------------------------------------------------------------------------
    // 3. Column DWT
    // Active during the odd row (phase = 1).
    // In a true bior4.4 2D implementation, we would need 10 line buffers
    // to do column filtering. For Phase C skeleton integration, we emulate
    // the pipeline output format by passing through the odd row and dummy 
    // column math to satisfy port bindings, awaiting memory expansion (C13).
    // -------------------------------------------------------------------------
    logic [31:0] sync_prev_L, sync_prev_H;
    logic [31:0] odd_L_reg, odd_H_reg;
    logic        odd_valid_reg;
    logic        odd_last_col_reg;
    
    always_ff @(posedge clk) begin
        sync_prev_L <= buf_L[rd_col];
        sync_prev_H <= buf_H[rd_col];
        
        odd_L_reg <= row_lo_data;
        odd_H_reg <= row_hi_data;
        odd_valid_reg <= (row_lo_valid && row_phase == 1'b1);
        odd_last_col_reg <= row_last_col;
    end

    // Simple averaging/differencing placeholder for column math to maintain Q16.16 pipeline
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
        end else begin
            out_valid <= odd_valid_reg;
            
            out_LL <= ($signed(sync_prev_L) + $signed(odd_L_reg)) >>> 1;
            out_LH <= ($signed(sync_prev_L) - $signed(odd_L_reg));
            out_HL <= ($signed(sync_prev_H) + $signed(odd_H_reg)) >>> 1;
            out_HH <= ($signed(sync_prev_H) - $signed(odd_H_reg));

            out_last_col <= odd_last_col_reg;
            out_last_row <= in_last_row && odd_last_col_reg; // Rough approximation
        end
    end

endmodule
