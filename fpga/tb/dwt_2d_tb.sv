`timescale 1ns/1ps

// Single-level 2D DWT test on a 4x4 image
module dwt_2d_tb;

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
            @(posedge clk);
            if (in_ready) begin
                in_valid    <= 1'b1;
                in_data     <= img_mem[idx];
                in_last_col <= ((idx % COLS) == COLS - 1);
                in_last_row <= (idx >= NUM_PIXELS - COLS);
                idx = idx + 1;
            end else begin
                in_valid <= 1'b0;
            end
        end
        @(posedge clk);
        in_valid <= 1'b0;

        wait(out_done == 1'b1);
        #100;
        $display("Total LL outputs: %0d (expected 36 = 6x6)", ll_count);
        $finish;
    end

    always @(posedge clk) begin
        if (out_valid) begin
            $display("LL[%0d] = %0d (%.4f)", ll_count, out_LL, $signed(out_LL) / 65536.0);
            ll_count = ll_count + 1;
        end
    end

    initial begin
        #50000000;
        $display("TIMEOUT");
        $finish;
    end

endmodule
