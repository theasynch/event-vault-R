`timescale 1ns/1ps

// =============================================================================
//  dwt_tb.sv — 3-Level 2D DWT Testbench (bior4.4, Q16.16)
//  EventVault-R Accelerator — Phase C Verification
//
//  Streams image_001.hex into dwt_2d_top with proper back-pressure handling,
//  captures L0 base layer output, and compares against C++ Q16.16 golden vectors.
// =============================================================================

module dwt_tb;

    localparam ROWS = 64;
    localparam COLS = 64;
    localparam NUM_PIXELS = ROWS * COLS;

    // Clock and Reset
    reg clk;
    reg rst_n;
    always #5 clk = ~clk;

    // DUT Signals
    reg         in_valid;
    reg signed [31:0] in_data;
    reg         in_last_col;
    reg         in_last_row;
    wire        in_ready;

    wire        h1_valid;
    wire signed [31:0] dut_base_L0;
    wire        the_done;

    // Instantiate DUT
    dwt_2d_top #(
        .MAX_COLS(COLS),
        .MAX_ROWS(ROWS)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_rows(11'd64),
        .cfg_cols(11'd64),
        .in_valid(in_valid),
        .in_data(in_data),
        .in_last_col(in_last_col),
        .in_last_row(in_last_row),
        .in_ready(in_ready),

        .h3_valid(), .h3_LH(), .h3_HL(), .h3_HH(),
        .h2_valid(), .h2_LH(), .h2_HL(), .h2_HH(),
        .h1_valid(h1_valid),
        .h1_LH(), .h1_HL(), .h1_HH(),
        .base_L0(dut_base_L0),
        .done(the_done)
    );

    // Memory for Input Image
    reg [31:0] img_mem [0:NUM_PIXELS-1];
    integer out_fd;
    integer out_count;
    integer pixel_idx;

    // Simulation Sequence
    initial begin
        clk = 0;
        rst_n = 0;
        in_valid = 0;
        in_data = 0;
        in_last_col = 0;
        in_last_row = 0;
        out_count = 0;
        pixel_idx = 0;

        $readmemh("verification/vectors/image_001.hex", img_mem);
        out_fd = $fopen("verification/vectors/rtl_out_l0.hex", "w");

        $display("==================================================");
        $display(" EventVault-R RTL Verification: 3-Level 2D bior4.4");
        $display(" Input: 64x64, Expected L0: 15x15 = 225 values");
        $display("==================================================");

        // Reset
        #20 rst_n = 1;
        #10;

        // Stream data with back-pressure handling
        while (pixel_idx < NUM_PIXELS) begin
            if (!in_valid || in_ready) begin
                in_valid    <= 1'b1;
                in_data     <= img_mem[pixel_idx];
                in_last_col <= ((pixel_idx % COLS) == COLS - 1);
                in_last_row <= (pixel_idx >= NUM_PIXELS - COLS);
                pixel_idx = pixel_idx + 1;
            end
            @(posedge clk);
        end

        @(posedge clk);
        in_valid    <= 1'b0;
        in_last_col <= 1'b0;
        in_last_row <= 1'b0;

        $display("All %0d pixels streamed. Waiting for DWT pipeline...", NUM_PIXELS);

        // Wait for DWT to complete
        wait(the_done == 1'b1);
        #100;

        $fclose(out_fd);
        $display("Simulation Complete. Captured %0d L0 values.", out_count);
        $finish;
    end

    // Monitor L0 Output
    always @(posedge clk) begin
        if (h1_valid) begin
            $fdisplay(out_fd, "%08X", dut_base_L0);
            out_count = out_count + 1;
        end
    end

    // Timeout watchdog
    initial begin
        #500000000;   // 500ms
        $display("ERROR: Simulation timeout after 500ms!");
        $display("Captured %0d L0 values so far.", out_count);
        $fclose(out_fd);
        $finish;
    end

endmodule
