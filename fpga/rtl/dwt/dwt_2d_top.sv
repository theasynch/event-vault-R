// =============================================================================
//  dwt_2d_top.sv — 3-Level 2D Bior4.4 DWT (Sequential Block-Based)
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V (DE1-SoC)
//
//  Orchestrates 3 sequential passes of dwt_2d_level.
//  Level 1: input image → H3 + LL1
//  Level 2: LL1 → H2 + LL2
//  Level 3: LL2 → H1 + L0
// =============================================================================

module dwt_2d_top #(
    parameter MAX_COLS = 64,
    parameter MAX_ROWS = 64
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

    output reg              h3_valid,
    output reg signed [31:0] h3_LH, h3_HL, h3_HH,

    output reg              h2_valid,
    output reg signed [31:0] h2_LH, h2_HL, h2_HH,

    output reg              h1_valid,
    output reg signed [31:0] h1_LH, h1_HL, h1_HH,
    output reg signed [31:0] base_L0,

    output reg              done
);

    localparam F = 10;
    localparam MAX_L1_DIM = (MAX_COLS + F - 1) / 2;
    localparam MAX_L2_DIM = (MAX_L1_DIM + F - 1) / 2;

    // State machine
    localparam [2:0] TOP_IDLE    = 3'd0;
    localparam [2:0] TOP_LEVEL1  = 3'd1;
    localparam [2:0] TOP_FEED_L2 = 3'd2;
    localparam [2:0] TOP_LEVEL2  = 3'd3;
    localparam [2:0] TOP_FEED_L3 = 3'd4;
    localparam [2:0] TOP_LEVEL3  = 3'd5;
    localparam [2:0] TOP_DONE    = 3'd6;

    reg [2:0] top_state;

    // Data feeds for Level 1
    reg         l1_in_valid;
    reg  signed [31:0] l1_in_data;
    reg         l1_in_last_col;
    reg         l1_in_last_row;
    wire        l1_in_ready;

    assign in_ready = (top_state == TOP_IDLE || top_state == TOP_LEVEL1) ? (!l1_in_valid || l1_in_ready) : 1'b0;
    wire             l1_out_valid, l1_out_done;
    wire signed [31:0] l1_LL, l1_LH, l1_HL, l1_HH;
    wire [10:0]      l1_out_rows, l1_out_cols;

    dwt_2d_level #(.MAX_ROWS(MAX_ROWS), .MAX_COLS(MAX_COLS)) level_1 (
        .clk(clk), .rst_n(rst_n),
        .cfg_rows(cfg_rows), .cfg_cols(cfg_cols),
        .in_valid(l1_in_valid), .in_data(l1_in_data),
        .in_last_col(l1_in_last_col), .in_last_row(l1_in_last_row),
        .in_ready(l1_in_ready),
        .out_valid(l1_out_valid), .out_LL(l1_LL), .out_LH(l1_LH),
        .out_HL(l1_HL), .out_HH(l1_HH),
        .out_rows(l1_out_rows), .out_cols(l1_out_cols),
        .out_done(l1_out_done)
    );

    // LL1 buffer
    reg signed [31:0] ll1_buf [0:MAX_L1_DIM*MAX_L1_DIM-1];
    reg [10:0] ll1_wr_ptr, ll1_rd_ptr;
    reg [10:0] ll1_rows, ll1_cols;

    // Level 2 signals
    reg              l2_in_valid;
    reg signed [31:0] l2_in_data;
    reg              l2_in_last_col, l2_in_last_row;
    wire             l2_in_ready;
    wire             l2_out_valid, l2_out_done;
    wire signed [31:0] l2_LL, l2_LH, l2_HL, l2_HH;
    wire [10:0]      l2_out_rows, l2_out_cols;

    dwt_2d_level #(.MAX_ROWS(MAX_L1_DIM), .MAX_COLS(MAX_L1_DIM)) level_2 (
        .clk(clk), .rst_n(rst_n),
        .cfg_rows(ll1_rows), .cfg_cols(ll1_cols),
        .in_valid(l2_in_valid), .in_data(l2_in_data),
        .in_last_col(l2_in_last_col), .in_last_row(l2_in_last_row),
        .in_ready(l2_in_ready),
        .out_valid(l2_out_valid), .out_LL(l2_LL), .out_LH(l2_LH),
        .out_HL(l2_HL), .out_HH(l2_HH),
        .out_rows(l2_out_rows), .out_cols(l2_out_cols),
        .out_done(l2_out_done)
    );

    // LL2 buffer
    reg signed [31:0] ll2_buf [0:MAX_L2_DIM*MAX_L2_DIM-1];
    reg [10:0] ll2_wr_ptr, ll2_rd_ptr;
    reg [10:0] ll2_rows, ll2_cols;

    // Level 3 signals
    reg              l3_in_valid;
    reg signed [31:0] l3_in_data;
    reg              l3_in_last_col, l3_in_last_row;
    wire             l3_in_ready;
    wire             l3_out_valid, l3_out_done;
    wire signed [31:0] l3_LL, l3_LH, l3_HL, l3_HH;
    wire [10:0]      l3_out_rows, l3_out_cols;

    dwt_2d_level #(.MAX_ROWS(MAX_L2_DIM), .MAX_COLS(MAX_L2_DIM)) level_3 (
        .clk(clk), .rst_n(rst_n),
        .cfg_rows(ll2_rows), .cfg_cols(ll2_cols),
        .in_valid(l3_in_valid), .in_data(l3_in_data),
        .in_last_col(l3_in_last_col), .in_last_row(l3_in_last_row),
        .in_ready(l3_in_ready),
        .out_valid(l3_out_valid), .out_LL(l3_LL), .out_LH(l3_LH),
        .out_HL(l3_HL), .out_HH(l3_HH),
        .out_rows(l3_out_rows), .out_cols(l3_out_cols),
        .out_done(l3_out_done)
    );

    // Feed counters
    reg [10:0] feed_row, feed_col;

    // Top controller
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            top_state    <= TOP_IDLE;
            l1_in_valid  <= 1'b0;
            l2_in_valid  <= 1'b0;
            l3_in_valid  <= 1'b0;
            ll1_wr_ptr   <= 0;
            ll1_rd_ptr   <= 0;
            ll2_wr_ptr   <= 0;
            ll2_rd_ptr   <= 0;
            h3_valid     <= 1'b0;
            h2_valid     <= 1'b0;
            h1_valid     <= 1'b0;
            done         <= 1'b0;
            feed_row     <= 0;
            feed_col     <= 0;
        end else begin
            l1_in_valid <= 1'b0;
            l2_in_valid <= 1'b0;
            l3_in_valid <= 1'b0;
            h3_valid    <= 1'b0;
            h2_valid    <= 1'b0;
            h1_valid    <= 1'b0;
            done        <= 1'b0;

            case (top_state)
                TOP_IDLE: begin
                    ll1_wr_ptr <= 0;
                    ll2_wr_ptr <= 0;
                    if (in_valid) begin
                        top_state      <= TOP_LEVEL1;
                        l1_in_valid    <= 1'b1;
                        l1_in_data     <= in_data;
                        l1_in_last_col <= in_last_col;
                        l1_in_last_row <= in_last_row;
                    end
                end

                TOP_LEVEL1: begin
                    if (!l1_in_valid || l1_in_ready) begin
                        l1_in_valid    <= in_valid && (top_state == TOP_LEVEL1);
                        l1_in_data     <= in_data;
                        l1_in_last_col <= in_last_col;
                        l1_in_last_row <= in_last_row;
                    end else begin
                        l1_in_valid <= l1_in_valid;
                    end

                    if (l1_out_valid) begin
                        h3_valid <= 1'b1;
                        h3_LH <= l1_LH; h3_HL <= l1_HL; h3_HH <= l1_HH;
                        ll1_buf[ll1_wr_ptr] <= l1_LL;
                        ll1_wr_ptr <= ll1_wr_ptr + 1;
                    end

                    if (l1_out_done) begin
                        ll1_rows  <= l1_out_rows;
                        ll1_cols  <= l1_out_cols;
                        ll1_rd_ptr <= 0;
                        feed_row  <= 0;
                        feed_col  <= 0;
                        top_state <= TOP_FEED_L2;
                    end
                end

                TOP_FEED_L2: begin
                    if (!l2_in_valid || l2_in_ready) begin
                        if (feed_row == ll1_rows) begin
                            l2_in_valid <= 1'b0;
                            top_state <= TOP_LEVEL2;
                        end else begin
                            l2_in_valid    <= 1'b1;
                            l2_in_data     <= ll1_buf[ll1_rd_ptr];
                            l2_in_last_col <= (feed_col == ll1_cols - 1);
                            l2_in_last_row <= (feed_row == ll1_rows - 1);
                            ll1_rd_ptr     <= ll1_rd_ptr + 1;

                            if (feed_col == ll1_cols - 1) begin
                                feed_col <= 0;
                                feed_row <= feed_row + 1;
                            end else begin
                                feed_col <= feed_col + 1;
                            end
                        end
                    end else begin
                        l2_in_valid <= l2_in_valid;
                    end
                end

                TOP_LEVEL2: begin
                    if (l2_out_valid) begin
                        h2_valid <= 1'b1;
                        h2_LH <= l2_LH; h2_HL <= l2_HL; h2_HH <= l2_HH;
                        ll2_buf[ll2_wr_ptr] <= l2_LL;
                        ll2_wr_ptr <= ll2_wr_ptr + 1;
                    end

                    if (l2_out_done) begin
                        ll2_rows  <= l2_out_rows;
                        ll2_cols  <= l2_out_cols;
                        ll2_rd_ptr <= 0;
                        feed_row  <= 0;
                        feed_col  <= 0;
                        top_state <= TOP_FEED_L3;
                    end
                end

                TOP_FEED_L3: begin
                    if (!l3_in_valid || l3_in_ready) begin
                        if (feed_row == ll2_rows) begin
                            l3_in_valid <= 1'b0;
                            top_state <= TOP_LEVEL3;
                        end else begin
                            l3_in_valid    <= 1'b1;
                            l3_in_data     <= ll2_buf[ll2_rd_ptr];
                            l3_in_last_col <= (feed_col == ll2_cols - 1);
                            l3_in_last_row <= (feed_row == ll2_rows - 1);
                            ll2_rd_ptr     <= ll2_rd_ptr + 1;

                            if (feed_col == ll2_cols - 1) begin
                                feed_col <= 0;
                                feed_row <= feed_row + 1;
                            end else begin
                                feed_col <= feed_col + 1;
                            end
                        end
                    end else begin
                        l3_in_valid <= l3_in_valid;
                    end
                end

                TOP_LEVEL3: begin
                    if (l3_out_valid) begin
                        h1_valid <= 1'b1;
                        h1_LH <= l3_LH; h1_HL <= l3_HL; h1_HH <= l3_HH;
                        base_L0 <= l3_LL;
                    end

                    if (l3_out_done) begin
                        done      <= 1'b1;
                        top_state <= TOP_DONE;
                    end
                end

                TOP_DONE: begin
                    top_state <= TOP_IDLE;
                end
            endcase
        end
    end

endmodule
