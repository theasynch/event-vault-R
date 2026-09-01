// =============================================================================
//  science_guardrail.sv — Photometric Flux & Centroid Evaluator
//  EventVault-R Accelerator — Science Module
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Evaluates the science guardrail condition (Eq. 13) for a reconstructed image.
//  Uses a 5x5 sliding window to compute:
//    Flux (F) = sum(I(x,y))
//    Centroid X = sum(x * I(x,y)) / F
//    Centroid Y = sum(y * I(x,y)) / F
//  To avoid division, it evaluates: |sum_x - ref_x * F| < eps_x * F
// =============================================================================

module science_guardrail #(
    parameter int PIXEL_W   = 16,
    parameter int LINE_COLS = 1024
)(
    input  logic                 clk,
    input  logic                 rst_n,

    // Reconstructed pixel stream (IDWT output)
    input  logic                 in_valid,
    input  logic [PIXEL_W-1:0]   in_data,
    input  logic                 in_last_col,
    input  logic                 in_last_row,

    // Reference source to check against
    input  logic                 check_en,
    input  logic [9:0]           ref_x,
    input  logic [9:0]           ref_y,
    input  logic [31:0]          ref_flux,      // From L0 extraction
    input  logic [15:0]          eps_flux_q15,  // e.g., 0.005 in Q15 = 163
    input  logic [15:0]          eps_cent_q15,  // e.g., 0.1 in Q15 = 3276

    // Output Decision
    output logic                 decision_valid,
    output logic                 is_safe        // 1 if within bounds, 0 if violated
);

    // -------------------------------------------------------------------------
    // 1. Line Buffers for 5x5 Window
    // -------------------------------------------------------------------------
    logic [$clog2(LINE_COLS)-1:0] rd_col;
    logic [PIXEL_W-1:0]           rd_data [0:4]; // 5 lines

    logic [$clog2(LINE_COLS)-1:0] col_cnt, row_cnt;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            col_cnt <= '0;
            row_cnt <= '0;
        end else if (in_valid) begin
            if (in_last_col) begin
                col_cnt <= '0;
                row_cnt <= (in_last_row) ? '0 : row_cnt + 1'b1;
            end else begin
                col_cnt <= col_cnt + 1'b1;
            end
        end
    end

    assign rd_col = col_cnt;

    line_buffer #(
        .PIXEL_W(PIXEL_W),
        .LINE_COLS(LINE_COLS),
        .NUM_LINES(5)
    ) lb5 (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (in_valid),
        .wr_data (in_data),
        .rd_col  (rd_col),
        .rd_data (rd_data)
    );

    // -------------------------------------------------------------------------
    // 2. Sliding 5x5 Window
    // -------------------------------------------------------------------------
    logic [PIXEL_W-1:0] win [0:4][0:4]; 

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i=0; i<5; i++)
                for (int j=0; j<5; j++)
                    win[i][j] <= '0;
        end else if (in_valid) begin
            for (int i=0; i<5; i++) begin
                win[i][0] <= win[i][1];
                win[i][1] <= win[i][2];
                win[i][2] <= win[i][3];
                win[i][3] <= win[i][4];
            end
            win[0][4] <= rd_data[0];
            win[1][4] <= rd_data[1];
            win[2][4] <= rd_data[2];
            win[3][4] <= rd_data[3];
            win[4][4] <= rd_data[4];
        end
    end

    // Center pixel is win[2][2], corresponding to (col_cnt-2, row_cnt-2)
    logic [9:0] center_x, center_y;
    always_comb begin
        center_x = col_cnt - 2;
        center_y = row_cnt - 2;
    end

    // -------------------------------------------------------------------------
    // 3. Accumulators (triggered when center matches ref)
    // -------------------------------------------------------------------------
    logic match_coord;
    assign match_coord = (center_x == ref_x) && (center_y == ref_y) && check_en;

    logic [31:0] sum_flux;
    logic signed [31:0] sum_dx; // sum of (dx * I)
    logic signed [31:0] sum_dy; // sum of (dy * I)

    // Pipeline stage 1: Add rows
    logic [31:0] row_sum [0:4];
    logic signed [31:0] row_sum_dx [0:4];
    
    always_ff @(posedge clk) begin
        if (in_valid) begin
            for (int i=0; i<5; i++) begin
                // flux sum for this row
                row_sum[i] <= win[i][0] + win[i][1] + win[i][2] + win[i][3] + win[i][4];
                
                // dx weighting: x relative to center (-2, -1, 0, 1, 2)
                row_sum_dx[i] <= $signed({1'b0, win[i][4]}) * 2 + 
                                 $signed({1'b0, win[i][3]}) * 1 - 
                                 $signed({1'b0, win[i][1]}) * 1 - 
                                 $signed({1'b0, win[i][0]}) * 2;
            end
        end
    end

    // Pipeline stage 2: Add all rows for final sums
    logic match_coord_p1, match_coord_p2;
    always_ff @(posedge clk) begin
        match_coord_p1 <= match_coord;
        match_coord_p2 <= match_coord_p1;
        
        if (in_valid) begin
            sum_flux <= row_sum[0] + row_sum[1] + row_sum[2] + row_sum[3] + row_sum[4];
            sum_dx   <= row_sum_dx[0] + row_sum_dx[1] + row_sum_dx[2] + row_sum_dx[3] + row_sum_dx[4];
            
            // dy weighting: y relative to center
            sum_dy   <= $signed(row_sum[4]) * 2 + 
                        $signed(row_sum[3]) * 1 - 
                        $signed(row_sum[1]) * 1 - 
                        $signed(row_sum[0]) * 2;
        end
    end

    // -------------------------------------------------------------------------
    // 4. Guardrail Condition Evaluation
    // -------------------------------------------------------------------------
    // Flux Error: |sum_flux - ref_flux| < eps_F * ref_flux
    // Centroid Error X: |sum_dx| < eps_x * sum_flux
    // Centroid Error Y: |sum_dy| < eps_x * sum_flux
    
    logic [31:0] abs_flux_diff;
    logic [31:0] abs_sum_dx, abs_sum_dy;
    
    always_comb begin
        abs_flux_diff = (sum_flux > ref_flux) ? (sum_flux - ref_flux) : (ref_flux - sum_flux);
        abs_sum_dx    = (sum_dx < 0) ? -sum_dx : sum_dx;
        abs_sum_dy    = (sum_dy < 0) ? -sum_dy : sum_dy;
    end

    // Need multipliers for bounds checking
    // Q15 bounds -> shift by 15
    logic [47:0] flux_bound;
    logic [47:0] cent_bound;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            decision_valid <= 1'b0;
            is_safe <= 1'b0;
        end else begin
            // Pipeline stage 3: multiplications
            flux_bound <= ref_flux * eps_flux_q15; 
            cent_bound <= sum_flux * eps_cent_q15;
            
            // Pipeline stage 4: decision
            decision_valid <= match_coord_p2;
            
            // Compare shifted values (Q0 against Q15 requires << 15 on the LHS)
            if (match_coord_p2) begin
                if (((abs_flux_diff << 15) <= flux_bound) && 
                    ((abs_sum_dx << 15) <= cent_bound) && 
                    ((abs_sum_dy << 15) <= cent_bound)) begin
                    is_safe <= 1'b1;
                end else begin
                    is_safe <= 1'b0;
                end
            end
        end
    end

endmodule
