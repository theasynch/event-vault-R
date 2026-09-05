`timescale 1ns/1ps

// =============================================================================
//  dwt_tb.sv — 2-D DWT Testbench
//  EventVault-R Accelerator — Phase C Verification
//
//  Reads `image_001.hex` (Q16.16 format) into memory, streams it to `dwt_2d_top`,
//  and dumps the Level 3 Base Layer (L0) to `rtl_out_l0.hex` for comparison.
// =============================================================================

module dwt_tb;

    // Simulation Parameters
    localparam int ROWS = 64; // Based on saved_discovery FITS dimensions
    localparam int COLS = 64;
    localparam int NUM_PIXELS = ROWS * COLS;

    // Clock and Reset
    logic clk;
    logic rst_n;

    always #5 clk = ~clk;

    // DUT Signals
    logic        in_valid;
    logic [31:0] in_data;
    logic        in_last_col;
    logic        in_last_row;

    logic        l3_valid;
    logic [31:0] base_L0;
    logic        done;

    // Instantiate DUT
    dwt_2d_top #(
        .LINE_COLS(COLS)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(in_valid),
        .in_data(in_data),
        .in_last_col(in_last_col),
        .in_last_row(in_last_row),
        
        .l1_valid(), .l1_LH(), .l1_HL(), .l1_HH(),
        .l2_valid(), .l2_LH(), .l2_HL(), .l2_HH(),
        .l3_valid(l3_valid), .l3_LH(), .l3_HL(), .l3_HH(),
        
        .base_L0(base_L0),
        .done(done)
    );

    // Memory for Input Image and Output
    logic [31:0] img_mem [0:NUM_PIXELS-1];
    int out_fd;

    // Simulation Sequence
    initial begin
        clk = 0;
        rst_n = 0;
        in_valid = 0;
        in_data = 0;
        in_last_col = 0;
        in_last_row = 0;

        // Load Hex Vector
        $readmemh("verification/vectors/image_001.hex", img_mem);
        out_fd = $fopen("verification/vectors/rtl_out_l0.hex", "w");

        $display("==================================================");
        $display(" EventVault-R RTL Verification: 2D DWT bior4.4");
        $display("==================================================");

        // Reset
        #20 rst_n = 1;
        #10;

        // Stream Data
        for (int i = 0; i < ROWS; i++) begin
            for (int j = 0; j < COLS; j++) begin
                @(posedge clk);
                in_valid <= 1'b1;
                in_data <= img_mem[i * COLS + j];
                in_last_col <= (j == COLS - 1);
                in_last_row <= (i == ROWS - 1);
            end
        end

        @(posedge clk);
        in_valid <= 1'b0;
        in_last_col <= 1'b0;
        in_last_row <= 1'b0;

        // Wait for DWT Pipeline to flush (fixed delay since dummy logic breaks `done` signal)
        #5000;
        
        $fclose(out_fd);
        $display("Simulation Complete. Output saved to rtl_out_l0.hex");
        $display("Run Python comparison script to verify PSNR.");
        $finish;
    end

    // Monitor Output
    always_ff @(posedge clk) begin
        if (l3_valid) begin
            $fdisplay(out_fd, "%08X", base_L0);
        end
    end

endmodule
