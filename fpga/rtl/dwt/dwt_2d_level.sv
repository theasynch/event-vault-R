// =============================================================================
//  dwt_2d_level.sv — 1-Level 2D Bior4.4 DWT (Block-Based)
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V (DE1-SoC)
//
//  Architecture:
//    Phase 1 — ROW DWT: For each row, feed into dwt_1d_bior and store L/H results.
//    Phase 2 — COLUMN DWT: For each column, feed L-col and H-col into two
//              dwt_1d_bior instances to get LL,LH,HL,HH.
//    Phase 3 — OUTPUT: Stream out LL, LH, HL, HH sub-bands.
// =============================================================================

module dwt_2d_level #(
    parameter MAX_ROWS = 64,
    parameter MAX_COLS = 64
)(
    input  wire             clk,
    input  wire             rst_n,

    input  wire [10:0]      cfg_rows,
    input  wire [10:0]      cfg_cols,

    input  wire             in_valid,
    input  wire signed [31:0] in_data,
    input  wire             in_last_col,
    input  wire             in_last_row,
    output wire             in_ready,

    output reg              out_valid,
    output reg signed [31:0] out_LL,
    output reg signed [31:0] out_LH,
    output reg signed [31:0] out_HL,
    output reg signed [31:0] out_HH,
    output reg [10:0]       out_rows,
    output reg [10:0]       out_cols,
    output reg              out_done
);

    localparam F = 10;
    localparam MAX_OUT_N = (MAX_COLS + F - 1) / 2;
    localparam MAX_OUT_M = (MAX_ROWS + F - 1) / 2;

    // Intermediate BRAMs
    (* ramstyle = "M10K" *) reg signed [31:0] L_rows [0:MAX_ROWS*MAX_OUT_N-1];
    (* ramstyle = "M10K" *) reg signed [31:0] H_rows [0:MAX_ROWS*MAX_OUT_N-1];
    (* ramstyle = "M10K" *) reg signed [31:0] res_LL [0:MAX_OUT_M*MAX_OUT_N-1];
    (* ramstyle = "M10K" *) reg signed [31:0] res_LH [0:MAX_OUT_M*MAX_OUT_N-1];
    (* ramstyle = "M10K" *) reg signed [31:0] res_HL [0:MAX_OUT_M*MAX_OUT_N-1];
    (* ramstyle = "M10K" *) reg signed [31:0] res_HH [0:MAX_OUT_M*MAX_OUT_N-1];

    // State machine
    localparam [3:0] ST_IDLE       = 4'd0;
    localparam [3:0] ST_ROW_LOAD   = 4'd1;
    localparam [3:0] ST_ROW_WAIT   = 4'd2;
    localparam [3:0] ST_COL_REQ    = 4'd3;
    localparam [3:0] ST_COL_FEED   = 4'd4;
    localparam [3:0] ST_COL_WAIT   = 4'd5;
    localparam [3:0] ST_OUTPUT_REQ = 4'd6;
    localparam [3:0] ST_OUTPUT     = 4'd7;
    localparam [3:0] ST_DONE       = 4'd8;

    reg [3:0] state;
    reg [10:0] row_idx, col_idx;
    reg [10:0] out_N_reg, out_M_reg;
    reg [10:0] row_out_ptr;
    reg [10:0] col_out_ptr_a, col_out_ptr_b;
    reg [10:0] col_feed_row;
    reg [10:0] out_row_idx, out_col_idx;
    reg [12:0] rd_addr;

    // 1-D DWT instance A (for rows, then L-columns)
    reg              dwt_a_in_valid;
    reg signed [31:0] dwt_a_in_data;
    reg              dwt_a_in_last;
    wire             dwt_a_in_ready;
    reg [10:0]       dwt_a_cfg_N;

    wire             dwt_a_lo_valid;
    wire signed [31:0] dwt_a_lo_data;
    wire             dwt_a_lo_last;
    wire             dwt_a_hi_valid;
    wire signed [31:0] dwt_a_hi_data;

    dwt_1d_bior #(.MAX_N(MAX_COLS > MAX_ROWS ? MAX_COLS : MAX_ROWS)) u_dwt_a (
        .clk(clk), .rst_n(rst_n),
        .cfg_N(dwt_a_cfg_N),
        .in_valid(dwt_a_in_valid), .in_data(dwt_a_in_data),
        .in_last(dwt_a_in_last), .in_ready(dwt_a_in_ready),
        .lo_valid(dwt_a_lo_valid), .lo_data(dwt_a_lo_data), .lo_last(dwt_a_lo_last),
        .hi_valid(dwt_a_hi_valid), .hi_data(dwt_a_hi_data), .hi_last()
    );

    // 1-D DWT instance B (for H-columns only)
    reg              dwt_b_in_valid;
    reg signed [31:0] dwt_b_in_data;
    reg              dwt_b_in_last;
    wire             dwt_b_in_ready;

    wire             dwt_b_lo_valid;
    wire signed [31:0] dwt_b_lo_data;
    wire             dwt_b_lo_last;
    wire             dwt_b_hi_valid;
    wire signed [31:0] dwt_b_hi_data;

    dwt_1d_bior #(.MAX_N(MAX_ROWS)) u_dwt_b (
        .clk(clk), .rst_n(rst_n),
        .cfg_N(cfg_rows),
        .in_valid(dwt_b_in_valid), .in_data(dwt_b_in_data),
        .in_last(dwt_b_in_last), .in_ready(dwt_b_in_ready),
        .lo_valid(dwt_b_lo_valid), .lo_data(dwt_b_lo_data), .lo_last(dwt_b_lo_last),
        .hi_valid(dwt_b_hi_valid), .hi_data(dwt_b_hi_data), .hi_last()
    );

    // Input ready passthrough
    assign in_ready = (state == ST_IDLE || state == ST_ROW_LOAD) ? dwt_a_in_ready : 1'b0;

    // RAM Read Registers
    reg signed [31:0] L_rd_data, H_rd_data;
    reg signed [31:0] res_LL_rd, res_LH_rd, res_HL_rd, res_HH_rd;
    always_ff @(posedge clk) begin
        L_rd_data <= L_rows[rd_addr];
        H_rd_data <= H_rows[rd_addr];
        res_LL_rd <= res_LL[rd_addr];
        res_LH_rd <= res_LH[rd_addr];
        res_HL_rd <= res_HL[rd_addr];
        res_HH_rd <= res_HH[rd_addr];
    end

    // Main unified controller (single always block to avoid race conditions)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state          <= ST_IDLE;
            row_idx        <= 0;
            col_idx        <= 0;
            out_valid      <= 1'b0;
            out_done       <= 1'b0;
            dwt_a_in_valid <= 1'b0;
            dwt_b_in_valid <= 1'b0;
            out_N_reg      <= 0;
            out_M_reg      <= 0;
            col_feed_row   <= 0;
            row_out_ptr    <= 0;
            col_out_ptr_a  <= 0;
            col_out_ptr_b  <= 0;
            out_row_idx    <= 0;
            out_col_idx    <= 0;
            rd_addr        <= 0;
        end else begin
            // Defaults
            out_valid      <= 1'b0;
            out_done       <= 1'b0;
            dwt_a_in_valid <= 1'b0;
            dwt_b_in_valid <= 1'b0;

            // --- Row DWT output capture (always active during row phase) ---
            if ((state == ST_ROW_LOAD || state == ST_ROW_WAIT) && dwt_a_lo_valid) begin
                L_rows[row_idx * MAX_OUT_N + row_out_ptr] <= dwt_a_lo_data;
                H_rows[row_idx * MAX_OUT_N + row_out_ptr] <= dwt_a_hi_data;
                row_out_ptr <= row_out_ptr + 1;
            end

            // --- Column DWT output capture (always active during col phase) ---
            if ((state == ST_COL_FEED || state == ST_COL_WAIT) && dwt_a_lo_valid) begin
                res_LL[col_out_ptr_a * MAX_OUT_N + col_idx] <= dwt_a_lo_data;
                res_LH[col_out_ptr_a * MAX_OUT_N + col_idx] <= dwt_a_hi_data;
                col_out_ptr_a <= col_out_ptr_a + 1;
            end
            if ((state == ST_COL_FEED || state == ST_COL_WAIT) && dwt_b_lo_valid) begin
                res_HL[col_out_ptr_b * MAX_OUT_N + col_idx] <= dwt_b_lo_data;
                res_HH[col_out_ptr_b * MAX_OUT_N + col_idx] <= dwt_b_hi_data;
                col_out_ptr_b <= col_out_ptr_b + 1;
            end

            // --- State machine ---
            case (state)
                ST_IDLE: begin
                    row_idx     <= 0;
                    col_idx     <= 0;
                    row_out_ptr <= 0;
                    out_N_reg   <= (cfg_cols + F - 1) / 2;
                    out_M_reg   <= (cfg_rows + F - 1) / 2;
                    if (in_valid) begin
                        dwt_a_cfg_N    <= cfg_cols;
                        dwt_a_in_valid <= 1'b1;
                        dwt_a_in_data  <= in_data;
                        dwt_a_in_last  <= in_last_col;
                        row_out_ptr    <= 0;
                        if (in_last_col)
                            state <= ST_ROW_WAIT;
                        else
                            state <= ST_ROW_LOAD;
                    end
                end

                ST_ROW_LOAD: begin
                    if (in_valid && dwt_a_in_ready) begin
                        dwt_a_in_valid <= 1'b1;
                        dwt_a_in_data  <= in_data;
                        dwt_a_in_last  <= in_last_col;
                        if (in_last_col)
                            state <= ST_ROW_WAIT;
                    end
                end

                ST_ROW_WAIT: begin
                    if (dwt_a_lo_valid && dwt_a_lo_last) begin
                        if (row_idx == cfg_rows - 1) begin
                            col_idx       <= 0;
                            col_feed_row  <= 0;
                            col_out_ptr_a <= 0;
                            col_out_ptr_b <= 0;
                            rd_addr       <= 0 * MAX_OUT_N + 0;
                            state         <= ST_COL_REQ;
                        end else begin
                            row_idx     <= row_idx + 1;
                            row_out_ptr <= 0;
                            state       <= ST_ROW_LOAD;
                        end
                    end
                end

                ST_COL_REQ: begin
                    if (dwt_a_in_ready && dwt_b_in_ready) begin
                        rd_addr <= (col_feed_row + 1) * MAX_OUT_N + col_idx; // request NEXT read
                        state <= ST_COL_FEED;
                    end
                end

                ST_COL_FEED: begin
                    dwt_a_cfg_N    <= cfg_rows;
                    dwt_a_in_valid <= 1'b1;
                    dwt_a_in_data  <= L_rd_data;
                    dwt_a_in_last  <= (col_feed_row == cfg_rows - 1);

                    dwt_b_in_valid <= 1'b1;
                    dwt_b_in_data  <= H_rd_data;
                    dwt_b_in_last  <= (col_feed_row == cfg_rows - 1);

                    if (col_feed_row == cfg_rows - 1)
                        state <= ST_COL_WAIT;
                    else begin
                        col_feed_row <= col_feed_row + 1;
                        rd_addr <= (col_feed_row + 2) * MAX_OUT_N + col_idx;
                    end
                end

                ST_COL_WAIT: begin
                    // Wait for BOTH column DWTs to finish
                    if (dwt_a_lo_valid && dwt_a_lo_last) begin
                        if (col_idx == out_N_reg - 1) begin
                            out_row_idx <= 0;
                            out_col_idx <= 0;
                            rd_addr     <= 0 * MAX_OUT_N + 0;
                            state       <= ST_OUTPUT_REQ;
                        end else begin
                            col_idx       <= col_idx + 1;
                            col_feed_row  <= 0;
                            col_out_ptr_a <= 0;
                            col_out_ptr_b <= 0;
                            rd_addr       <= 0 * MAX_OUT_N + (col_idx + 1);
                            state         <= ST_COL_REQ;
                        end
                    end
                end

                ST_OUTPUT_REQ: begin
                    rd_addr <= out_row_idx * MAX_OUT_N + (out_col_idx + 1);
                    state <= ST_OUTPUT;
                end

                ST_OUTPUT: begin
                    out_valid <= 1'b1;
                    out_LL    <= res_LL_rd;
                    out_LH    <= res_LH_rd;
                    out_HL    <= res_HL_rd;
                    out_HH    <= res_HH_rd;
                    out_rows  <= out_M_reg;
                    out_cols  <= out_N_reg;

                    if (out_col_idx == out_N_reg - 1) begin
                        out_col_idx <= 0;
                        if (out_row_idx == out_M_reg - 1) begin
                            out_done <= 1'b1;
                            state    <= ST_DONE;
                        end else begin
                            out_row_idx <= out_row_idx + 1;
                            rd_addr <= (out_row_idx + 1) * MAX_OUT_N + 0;
                        end
                    end else begin
                        out_col_idx <= out_col_idx + 1;
                        if (out_col_idx + 1 == out_N_reg - 1)
                            rd_addr <= out_row_idx * MAX_OUT_N + (out_col_idx + 2);
                        else
                            rd_addr <= out_row_idx * MAX_OUT_N + (out_col_idx + 2);
                    end
                end

                ST_DONE: begin
                    state <= ST_IDLE;
                end
            endcase
        end
    end

endmodule
