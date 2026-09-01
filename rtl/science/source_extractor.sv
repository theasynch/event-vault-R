// =============================================================================
//  source_extractor.sv — Hardware Peak Detection (Source Extraction)
//  EventVault-R Accelerator — Science Module
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Detects astronomical sources in the streaming L0 (Base Layer).
//  Uses a 3x3 sliding window (via line_buffer) to find local maxima
//  that exceed a configurable threshold.
// =============================================================================

module source_extractor #(
    parameter int PIXEL_W   = 19, // L0 is IN_W+3 = 16+3=19
    parameter int LINE_COLS = 128 // 1024 / (2^3)
)(
    input  logic                 clk,
    input  logic                 rst_n,

    // Config
    input  logic [PIXEL_W-1:0]   threshold,

    // Streaming L0 input
    input  logic                 in_valid,
    input  logic [PIXEL_W-1:0]   in_data,
    input  logic                 in_last_col,
    input  logic                 in_last_row,

    // Detected sources output (stream)
    output logic                 source_valid,
    output logic [9:0]           source_x, // Up to 1024 mapped
    output logic [9:0]           source_y,
    output logic [PIXEL_W-1:0]   source_flux
);

    // -------------------------------------------------------------------------
    // 1. Line Buffer for 3x3 Window
    // -------------------------------------------------------------------------
    logic [$clog2(LINE_COLS)-1:0] rd_col;
    logic [PIXEL_W-1:0]           rd_data [0:2]; // 3 lines

    // We write when valid. The line buffer internally auto-increments wr_col.
    // We read from the same column we are currently writing to, effectively 
    // getting the current pixel and the two previous rows' pixels at this column.
    
    // We need to delay rd_col to match our sliding window. 
    // Actually, line_buffer provides read data combinatorially based on rd_col.
    // Let's track the current column we are writing to.
    logic [$clog2(LINE_COLS)-1:0] col_cnt;
    logic [$clog2(LINE_COLS)-1:0] row_cnt;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            col_cnt <= '0;
            row_cnt <= '0;
        end else if (in_valid) begin
            if (in_last_col) begin
                col_cnt <= '0;
                if (in_last_row)
                    row_cnt <= '0;
                else
                    row_cnt <= row_cnt + 1'b1;
            end else begin
                col_cnt <= col_cnt + 1'b1;
            end
        end
    end

    assign rd_col = col_cnt;

    line_buffer #(
        .PIXEL_W(PIXEL_W),
        .LINE_COLS(LINE_COLS),
        .NUM_LINES(3)
    ) lb (
        .clk     (clk),
        .rst_n   (rst_n),
        .wr_en   (in_valid),
        .wr_data (in_data),
        .rd_col  (rd_col),
        .rd_data (rd_data)
    );

    // -------------------------------------------------------------------------
    // 2. Sliding 3x3 Window Registers
    // -------------------------------------------------------------------------
    // Shift registers for the 3 columns of the 3x3 window
    logic [PIXEL_W-1:0] win [0:2][0:2]; // win[row][col]

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i=0; i<3; i++)
                for (int j=0; j<3; j++)
                    win[i][j] <= '0;
        end else if (in_valid) begin
            // Shift left
            for (int i=0; i<3; i++) begin
                win[i][0] <= win[i][1];
                win[i][1] <= win[i][2];
            end
            // Load new column (from line buffer)
            win[0][2] <= rd_data[0]; // Newest row (N)
            win[1][2] <= rd_data[1]; // Middle row (N-1)
            win[2][2] <= rd_data[2]; // Oldest row (N-2)
        end
    end

    // -------------------------------------------------------------------------
    // 3. Peak Detection Logic
    // -------------------------------------------------------------------------
    // Center pixel is win[1][1]. It belongs to row_cnt-1 and col_cnt-1.
    logic is_peak;
    logic exceeds_thresh;

    // Check if center is strictly greater than all 8 neighbors
    always_comb begin
        is_peak = 1'b1;
        for (int i=0; i<3; i++) begin
            for (int j=0; j<3; j++) begin
                if (!(i == 1 && j == 1)) begin
                    // Signed comparison because DWT outputs can be negative
                    if ($signed(win[1][1]) <= $signed(win[i][j])) begin
                        is_peak = 1'b0;
                    end
                end
            end
        end
    end

    assign exceeds_thresh = ($signed(win[1][1]) > $signed(threshold));

    // Valid only when we have at least 3 rows and are not at edges
    logic valid_window;
    // Pipelined coordinate logic
    logic [$clog2(LINE_COLS)-1:0] center_col;
    logic [$clog2(LINE_COLS)-1:0] center_row;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            center_col <= '0;
            center_row <= '0;
            valid_window <= 1'b0;
        end else if (in_valid) begin
            center_col <= col_cnt - 1'b1;
            center_row <= row_cnt - 1'b1;
            // valid when col >= 2 and row >= 2
            valid_window <= (col_cnt >= 2) && (row_cnt >= 2);
        end
    end

    // -------------------------------------------------------------------------
    // 4. Output Registered
    // -------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            source_valid <= 1'b0;
            source_x     <= '0;
            source_y     <= '0;
            source_flux  <= '0;
        end else begin
            // In same cycle as window shifts, we evaluate the PREVIOUS window state
            // But we actually evaluated combinatorial on the current win state.
            // Let's delay the evaluation by 1 cycle to align with valid_window.
            
            // Wait, we need to map the L0 coordinate (0..127) to original image (0..1023)
            // L0 is 1/8th scale (3 levels), so original coord is L0_coord * 8 + 4 (center)
            
            if (valid_window && is_peak && exceeds_thresh) begin
                source_valid <= 1'b1;
                source_x     <= (center_col << 3) + 4;
                source_y     <= (center_row << 3) + 4;
                source_flux  <= win[1][1]; // Approximate flux as peak L0 value
            end else begin
                source_valid <= 1'b0;
            end
        end
    end

endmodule
