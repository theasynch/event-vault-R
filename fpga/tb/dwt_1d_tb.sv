`timescale 1ns/1ps

// =============================================================================
//  dwt_1d_tb.sv — Minimal 1-D DWT testbench
//  Tests a 4-element input: [1.0, 2.0, 3.0, 4.0] in Q16.16
//  against Python reference output.
// =============================================================================

module dwt_1d_tb;

    reg clk, rst_n;
    always #5 clk = ~clk;

    reg         in_valid;
    reg signed [31:0] in_data;
    reg         in_last;
    wire        in_ready;

    wire        lo_valid, hi_valid;
    wire signed [31:0] lo_data, hi_data;
    wire        lo_last;

    dwt_1d_bior #(.MAX_N(64)) uut (
        .clk(clk), .rst_n(rst_n),
        .cfg_N(11'd64),
        .in_valid(in_valid), .in_data(in_data),
        .in_last(in_last), .in_ready(in_ready),
        .lo_valid(lo_valid), .lo_data(lo_data), .lo_last(lo_last),
        .hi_valid(hi_valid), .hi_data(hi_data), .hi_last()
    );

    reg signed [31:0] test_data [0:63];
    integer idx;
    integer lo_count, hi_count;

    initial begin
        $readmemh("verification/vectors/test_64.hex", test_data);

        clk = 0; rst_n = 0;
        in_valid = 0; in_data = 0; in_last = 0;
        lo_count = 0; hi_count = 0;
        idx = 0;

        #20 rst_n = 1;
        #10;

        // Feed 64 samples
        while (idx < 64) begin
            if (!in_valid || in_ready) begin
                in_valid <= 1'b1;
                in_data  <= test_data[idx];
                in_last  <= (idx == 63);
                idx = idx + 1;
            end
            @(posedge clk);
        end
        
        while (in_valid && !in_ready) @(posedge clk);
        in_valid <= 1'b0;

        // Wait for outputs
        #5000;

        $display("Lo outputs: %0d, Hi outputs: %0d", lo_count, hi_count);
        $writememh("verification/vectors/rtl_out_lo.hex", lo_mem);
        $finish;
    end

    reg [31:0] lo_mem [0:35];
    always @(posedge clk) begin
        if (lo_valid) begin
            $display("LO[%0d] = %0d (%.4f)  last=%b",
                lo_count, $signed(lo_data), $signed(lo_data) / 65536.0, lo_last);
            lo_mem[lo_count] = lo_data;
            lo_count = lo_count + 1;
        end
        if (hi_valid) begin
            $display("HI[%0d] = %0d (%.4f)",
                hi_count, $signed(hi_data), $signed(hi_data) / 65536.0);
            hi_count = hi_count + 1;
        end
    end

endmodule
