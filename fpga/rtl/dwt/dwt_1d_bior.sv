// =============================================================================
//  dwt_1d_bior.sv — 1-D Biorthogonal 4.4 DWT with Symmetric Boundary
//  EventVault-R Accelerator — DWT Engine
//  Target: Intel Cyclone V (DE1-SoC)
//
//  Implements the EXACT algorithm from dwt_fixed.cpp conv1d_dwt():
//    out_len = (N + F - 1) / 2   where F = 10
//    for k = 0 .. out_len-1:
//        for j = 0 .. F-1:
//            i = 2*k + 1 - j
//            i = symmetric_reflect(i, N)
//            s_lo += x[i] * f_lo[j]
//            s_hi += x[i] * f_hi[j]
//        out_lo[k] = s_lo >> 16
//        out_hi[k] = s_hi >> 16
//
//  Architecture: Block-based (store row, then compute).
// =============================================================================

module dwt_1d_bior #(
    parameter Q_FRACT_W = 16,
    parameter IN_W      = 32,
    parameter OUT_W     = 32,
    parameter MAX_N     = 1024
)(
    input  wire             clk,
    input  wire             rst_n,

    input  wire [10:0]      cfg_N,

    input  wire             in_valid,
    input  wire signed [IN_W-1:0]  in_data,
    input  wire             in_last,
    output reg              in_ready,

    output reg              lo_valid,
    output reg signed [OUT_W-1:0] lo_data,
    output reg              lo_last,

    output reg              hi_valid,
    output reg signed [OUT_W-1:0] hi_data,
    output reg              hi_last
);

    // Q16.16 Bior4.4 Coefficients (stored as individual parameters)
    localparam signed [31:0] L0_C =  32'sd0;
    localparam signed [31:0] L1_C =  32'sd2479;
    localparam signed [31:0] L2_C = -32'sd1563;
    localparam signed [31:0] L3_C = -32'sd7250;
    localparam signed [31:0] L4_C =  32'sd24733;
    localparam signed [31:0] L5_C =  32'sd55882;
    localparam signed [31:0] L6_C =  32'sd24733;
    localparam signed [31:0] L7_C = -32'sd7250;
    localparam signed [31:0] L8_C = -32'sd1563;
    localparam signed [31:0] L9_C =  32'sd2479;

    localparam signed [31:0] H0_C =  32'sd0;
    localparam signed [31:0] H1_C = -32'sd4229;
    localparam signed [31:0] H2_C =  32'sd2666;
    localparam signed [31:0] H3_C =  32'sd27400;
    localparam signed [31:0] H4_C = -32'sd51674;
    localparam signed [31:0] H5_C =  32'sd27400;
    localparam signed [31:0] H6_C =  32'sd2666;
    localparam signed [31:0] H7_C = -32'sd4229;
    localparam signed [31:0] H8_C =  32'sd0;
    localparam signed [31:0] H9_C =  32'sd0;

    localparam F = 10;

    // Input buffer
    (* ramstyle = "M10K" *) reg signed [IN_W-1:0] x_buf [0:MAX_N-1];
    reg [10:0] wr_ptr;
    reg [10:0] N_reg;
    reg [10:0] out_len;

    // State machine
    localparam [2:0] S_IDLE    = 3'd0;
    localparam [2:0] S_LOAD    = 3'd1;
    localparam [2:0] S_COMPUTE = 3'd2;
    localparam [2:0] S_OUTPUT  = 3'd3;
    localparam [2:0] S_DONE    = 3'd4;

    reg [2:0] state;
    reg [10:0] k_cnt;
    reg [3:0]  j_cnt, j_cnt_d1;
    reg        valid_mac;
    reg signed [63:0] acc_lo, acc_hi;

    // Address calculation for symmetric boundary reflection
    wire signed [12:0] raw_idx;
    reg [10:0] refl_idx;

    // Must use signed arithmetic: 2*k+1-j can be negative
    assign raw_idx = $signed({2'b0, k_cnt}) * 2 + 1 - $signed({9'b0, j_cnt});

    // Multi-pass reflection (C++ uses while loop; we unroll 2 passes)
    reg signed [12:0] pass1;
    always @(*) begin
        // Pass 1
        if (raw_idx < 0)
            pass1 = -1 - raw_idx;
        else if (raw_idx >= $signed({2'b0, N_reg}))
            pass1 = 2 * $signed({2'b0, N_reg}) - 1 - raw_idx;
        else
            pass1 = raw_idx;

        // Pass 2 (needed when F > N)
        if (pass1 < 0)
            refl_idx = -1 - pass1;
        else if (pass1 >= $signed({2'b0, N_reg}))
            refl_idx = 2 * N_reg - 1 - pass1;
        else
            refl_idx = pass1[10:0];
    end

    // Read sample and get coefficient
    reg signed [IN_W-1:0] x_val;
    
    // Coefficient lookup
    reg signed [31:0] coeff_lo, coeff_hi;
    always @(*) begin
        case (j_cnt)
            4'd0: begin coeff_lo = L0_C; coeff_hi = H0_C; end
            4'd1: begin coeff_lo = L1_C; coeff_hi = H1_C; end
            4'd2: begin coeff_lo = L2_C; coeff_hi = H2_C; end
            4'd3: begin coeff_lo = L3_C; coeff_hi = H3_C; end
            4'd4: begin coeff_lo = L4_C; coeff_hi = H4_C; end
            4'd5: begin coeff_lo = L5_C; coeff_hi = H5_C; end
            4'd6: begin coeff_lo = L6_C; coeff_hi = H6_C; end
            4'd7: begin coeff_lo = L7_C; coeff_hi = H7_C; end
            4'd8: begin coeff_lo = L8_C; coeff_hi = H8_C; end
            4'd9: begin coeff_lo = L9_C; coeff_hi = H9_C; end
            default: begin coeff_lo = 0; coeff_hi = 0; end
        endcase
    end

    reg signed [31:0] coeff_lo_d1, coeff_hi_d1;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= S_IDLE;
            wr_ptr   <= 0;
            k_cnt    <= 0;
            j_cnt    <= 0;
            j_cnt_d1 <= 0;
            valid_mac <= 1'b0;
            acc_lo   <= 0;
            acc_hi   <= 0;
            lo_valid <= 1'b0;
            hi_valid <= 1'b0;
            lo_last  <= 1'b0;
            hi_last  <= 1'b0;
            in_ready <= 1'b1;
            N_reg    <= 0;
            out_len  <= 0;
            x_val    <= 0;
            coeff_lo_d1 <= 0;
            coeff_hi_d1 <= 0;
        end else begin
            lo_valid <= 1'b0;
            hi_valid <= 1'b0;
            
            // Synchronous block RAM read
            x_val <= x_buf[refl_idx];
            coeff_lo_d1 <= coeff_lo;
            coeff_hi_d1 <= coeff_hi;

            case (state)
                S_IDLE: begin
                    in_ready <= 1'b1;
                    wr_ptr   <= 0;
                    k_cnt    <= 0;
                    valid_mac <= 1'b0;
                    if (in_valid) begin
                        x_buf[0] <= in_data;
                        wr_ptr   <= 1;
                        N_reg    <= cfg_N;
                        out_len  <= (cfg_N + F - 1) / 2;
                        if (in_last) begin
                            state    <= S_COMPUTE;
                            in_ready <= 1'b0;
                            j_cnt    <= 0;
                            acc_lo   <= 0;
                            acc_hi   <= 0;
                        end else begin
                            state <= S_LOAD;
                        end
                    end
                end

                S_LOAD: begin
                    in_ready <= 1'b1;
                    if (in_valid) begin
                        x_buf[wr_ptr] <= in_data;
                        wr_ptr <= wr_ptr + 1;
                        if (in_last) begin
                            state    <= S_COMPUTE;
                            in_ready <= 1'b0;
                            j_cnt    <= 0;
                            acc_lo   <= 0;
                            acc_hi   <= 0;
                        end
                    end
                end

                S_COMPUTE: begin
                    in_ready <= 1'b0;
                    
                    if (j_cnt < F) begin
                        j_cnt <= j_cnt + 1;
                        valid_mac <= 1'b1;
                    end else begin
                        valid_mac <= 1'b0;
                    end
                    
                    j_cnt_d1 <= j_cnt;
                    
                    if (valid_mac) begin
                        acc_lo <= acc_lo + (x_val * coeff_lo_d1);
                        acc_hi <= acc_hi + (x_val * coeff_hi_d1);
                        
                        if (j_cnt_d1 == F - 1) begin
                            state <= S_OUTPUT;
                            valid_mac <= 1'b0;
                        end
                    end
                end

                S_OUTPUT: begin
                    lo_valid <= 1'b1;
                    hi_valid <= 1'b1;
                    lo_data  <= acc_lo >>> Q_FRACT_W;
                    hi_data  <= acc_hi >>> Q_FRACT_W;
                    lo_last  <= (k_cnt == out_len - 1);
                    hi_last  <= (k_cnt == out_len - 1);

                    if (k_cnt == out_len - 1) begin
                        state <= S_DONE;
                    end else begin
                        k_cnt  <= k_cnt + 1;
                        j_cnt  <= 0;
                        acc_lo <= 0;
                        acc_hi <= 0;
                        state  <= S_COMPUTE;
                    end
                end

                S_DONE: begin
                    state    <= S_IDLE;
                    in_ready <= 1'b1;
                    k_cnt    <= 0;
                end
            endcase
        end
    end

endmodule
