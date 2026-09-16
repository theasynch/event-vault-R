`timescale 1ns/1ps

module guardrail_tb;

    reg clk, rst_n;
    always #5 clk = ~clk;

    reg in_valid, in_last_col, in_last_row;
    reg [31:0] in_data;
    
    reg check_en;
    reg [9:0] ref_x, ref_y;
    reg [31:0] ref_flux;
    reg [15:0] eps_flux_q15, eps_cent_q15;

    wire decision_valid, is_safe;

    science_guardrail #(
        .PIXEL_W(32),
        .LINE_COLS(64)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(in_valid),
        .in_data(in_data),
        .in_last_col(in_last_col),
        .in_last_row(in_last_row),
        .check_en(check_en),
        .ref_x(ref_x),
        .ref_y(ref_y),
        .ref_flux(ref_flux),
        .eps_flux_q15(eps_flux_q15),
        .eps_cent_q15(eps_cent_q15),
        .decision_valid(decision_valid),
        .is_safe(is_safe)
    );

    integer r, c;
    
    reg captured_decision_valid;
    reg captured_is_safe;
    
    always @(posedge clk) begin
        if (decision_valid) begin
            captured_decision_valid <= 1'b1;
            captured_is_safe <= is_safe;
        end
    end
    
    initial begin
        clk = 0; rst_n = 0;
        in_valid = 0; in_data = 0; in_last_col = 0; in_last_row = 0;
        check_en = 0; ref_x = 0; ref_y = 0; ref_flux = 0;
        eps_flux_q15 = 163;  // 0.005 in Q15
        eps_cent_q15 = 3276; // 0.1 in Q15
        captured_decision_valid = 0;
        
        #20 rst_n = 1;
        #10;
        $display("TEST mem[0][0] = %0d", dut.lb5.mem[0][0]);
        $display("TEST mem[0][33] = %0d", dut.lb5.mem[0][33]);
        // a 5x5 block at (center_x=30, center_y=20) which is filled with 10s.
        // sum = 25 * 10 = 250.
        check_en = 1;
        ref_x = 30;
        ref_y = 20;
        ref_flux = 250; 
        
        for (r = 0; r < 64; r = r + 1) begin
            for (c = 0; c < 64; c = c + 1) begin
                @(posedge clk);
                in_valid <= 1'b1;
                
                if (r >= 18 && r <= 22 && c >= 28 && c <= 32)
                    in_data <= 10;
                else
                    in_data <= 0;
                    
                in_last_col <= (c == 63);
                in_last_row <= (r == 63);
            end
        end
        @(posedge clk);
        in_valid <= 0;
        
        $display("Guardrail Decision Valid! is_safe = %b (Expected: 1)", captured_is_safe);
        
        // Now test a violation (flux mismatch)
        check_en = 0;
        captured_decision_valid = 0;
        #50;
        check_en = 1;
        ref_flux = 300; // Will violate eps_flux (250 vs 300 is > 0.005 error)
        for (r = 0; r < 64; r = r + 1) begin
            for (c = 0; c < 64; c = c + 1) begin
                @(posedge clk);
                in_valid <= 1'b1;
                if (r >= 18 && r <= 22 && c >= 28 && c <= 32) in_data <= 10;
                else in_data <= 0;
                in_last_col <= (c == 63);
                in_last_row <= (r == 63);
            end
        end
        @(posedge clk);
        in_valid <= 0;
        
        $display("Guardrail Decision Valid! is_safe = %b (Expected: 0)", captured_is_safe);
        
        // Now test a violation (centroid mismatch)
        check_en = 0;
        captured_decision_valid = 0;
        #50;
        check_en = 1;
        ref_flux = 250;
        for (r = 0; r < 64; r = r + 1) begin
            for (c = 0; c < 64; c = c + 1) begin
                @(posedge clk);
                in_valid <= 1'b1;
                // Shift the centroid to right by 1 pixel -> x centroid becomes 31 instead of 30!
                // Error = 1.0 > eps_x (0.1).
                if (r >= 18 && r <= 22 && c >= 29 && c <= 33) in_data <= 10;
                else in_data <= 0;
                in_last_col <= (c == 63);
                in_last_row <= (r == 63);
            end
        end
        @(posedge clk);
        in_valid <= 0;
        
        $display("Guardrail Decision Valid! is_safe = %b (Expected: 0)", captured_is_safe);
        
        #100;
        $finish;
    end

endmodule
