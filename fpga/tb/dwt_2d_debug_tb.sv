`timescale 1ns/1ps

// Debug 2D DWT testbench — dumps row DWT intermediates and final LL
module dwt_2d_debug_tb;

    localparam ROWS = 4;
    localparam COLS = 4;
    localparam NUM_PIXELS = ROWS * COLS;

    reg clk, rst_n;
    always #5 clk = ~clk;

    reg         in_valid;
    reg signed [31:0] in_data;
    reg         in_last_col, in_last_row;
    wire        in_ready;

    wire        out_valid, out_done;
    wire signed [31:0] out_LL, out_LH, out_HL, out_HH;
    wire [10:0] out_rows, out_cols;

    dwt_2d_level #(.MAX_ROWS(ROWS), .MAX_COLS(COLS)) dut (
        .clk(clk), .rst_n(rst_n),
        .cfg_rows(11'd4), .cfg_cols(11'd4),
        .in_valid(in_valid), .in_data(in_data),
        .in_last_col(in_last_col), .in_last_row(in_last_row),
        .in_ready(in_ready),
        .out_valid(out_valid), .out_LL(out_LL), .out_LH(out_LH),
        .out_HL(out_HL), .out_HH(out_HH),
        .out_rows(out_rows), .out_cols(out_cols),
        .out_done(out_done)
    );

    reg [31:0] img_mem [0:NUM_PIXELS-1];
    integer idx, ll_count;

    initial begin
        $readmemh("verification/vectors/test_4x4.hex", img_mem);
        clk = 0; rst_n = 0;
        in_valid = 0; in_data = 0; in_last_col = 0; in_last_row = 0;
        idx = 0; ll_count = 0;

        #20 rst_n = 1; #10;

        while (idx < NUM_PIXELS) begin
            if (!in_valid || in_ready) begin
                in_valid    <= 1'b1;
                in_data     <= img_mem[idx];
                in_last_col <= ((idx % COLS) == COLS - 1);
                in_last_row <= (idx >= NUM_PIXELS - COLS);
                idx = idx + 1;
            end
            @(posedge clk);
        end
        @(posedge clk);
        in_valid <= 1'b0;

        wait(out_done == 1'b1);
        #100;
        $display("Total LL outputs: %0d", ll_count);
        $finish;
    end

    // Monitor row DWT outputs
    always @(posedge clk) begin
        if (dut.u_dwt_a.lo_valid &&
            (dut.state == 3'd1 || dut.state == 3'd2)) begin // ST_ROW_LOAD or ST_ROW_WAIT
            $display("ROW[%0d] LO[%0d] = %0d (%.4f)",
                dut.row_idx, dut.row_out_ptr,
                $signed(dut.u_dwt_a.lo_data),
                $signed(dut.u_dwt_a.lo_data) / 65536.0);
        end
    end

    // Monitor row DWT inputs
    always @(posedge clk) begin
        if (in_valid || in_ready) begin
            $display("[TB] in_ready=%b in_valid=%b in_data=%.4f (idx=%0d)", in_ready, in_valid, $signed(in_data)/65536.0, idx);
        end
        if (dut.dwt_a_in_valid) begin
            $display("[DWT_A_IN] valid=%b data=%.4f", dut.dwt_a_in_valid, $signed(dut.dwt_a_in_data)/65536.0);
        end
    end

    // Monitor column DWT feeding
    always @(posedge clk) begin
        if (dut.dwt_a_in_valid &&
            (dut.state == 3'd3)) begin // ST_COL_FEED
            $display("COL_FEED col=%0d row=%0d L_val=%.4f",
                dut.col_idx, dut.col_feed_row,
                $signed(dut.dwt_a_in_data) / 65536.0);
        end
    end

    // Monitor LL outputs
    always @(posedge clk) begin
        if (out_valid) begin
            $display("LL[%0d] = %.4f", ll_count,
                $signed(out_LL) / 65536.0);
            ll_count = ll_count + 1;
        end
    end

    initial begin
        #50000000;
        $display("TIMEOUT");
        $finish;
    end

endmodule
