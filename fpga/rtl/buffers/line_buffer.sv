// =============================================================================
//  line_buffer.sv — Multi-Line Circular Image Line Buffer
//  EventVault-R Accelerator — Common Library
//  Target: Intel Cyclone V (DE1-SoC)
//
//  Provides NUM_LINES simultaneous read outputs for kernel operations.
//  Each read port gives the pixel from a different past row at the SAME
//  column position — used by the Sobel gradient, box filter, and DWT
//  column-direction stages.
//
//  Synthesis: Each line stored in a dedicated M10K BRAM row.
//  Parameters:
//    PIXEL_W   : bits per pixel
//    LINE_COLS : pixels per line (max 1024 for 1024×1024 frames)
//    NUM_LINES : lines buffered simultaneously (e.g., 3 for Sobel 3×3)
// =============================================================================

module line_buffer #(
    parameter int PIXEL_W   = 16,
    parameter int LINE_COLS = 1024,
    parameter int NUM_LINES = 3
)(
    input  logic                  clk,
    input  logic                  rst_n,

    // Write port — one pixel per cycle, column address auto-increments
    input  logic                  wr_en,
    input  logic [PIXEL_W-1:0]    wr_data,

    // Read port — same column from each of the NUM_LINES most recent rows
    input  logic [$clog2(LINE_COLS)-1:0] rd_col,          // column address for reads
    output logic [NUM_LINES*PIXEL_W-1:0] rd_data_flat
);

    localparam int COL_ADDR_W = $clog2(LINE_COLS);

    // -------------------------------------------------------------------------
    //  Internal write address counter
    // -------------------------------------------------------------------------
    logic [COL_ADDR_W-1:0] wr_col;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            wr_col <= '0;
        else if (wr_en)
            wr_col <= (wr_col == LINE_COLS - 1) ? '0 : wr_col + 1'b1;
    end

    // -------------------------------------------------------------------------
    //  Line rotate pointer — which "slot" receives the new line
    // -------------------------------------------------------------------------
    logic [$clog2(NUM_LINES)-1:0] wr_line;
    logic                         line_end;   // pulses when wr_col wraps to 0

    assign line_end = wr_en && (wr_col == LINE_COLS - 1);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            wr_line <= '0;
        else if (line_end)
            wr_line <= (wr_line == NUM_LINES - 1) ? '0 : wr_line + 1'b1;
    end

    // -------------------------------------------------------------------------
    //  BRAM storage: NUM_LINES × LINE_COLS × PIXEL_W
    //  Synthesized to NUM_LINES M10K blocks (one per line slot)
    // -------------------------------------------------------------------------
    logic [PIXEL_W-1:0] mem [0:NUM_LINES-1][0:LINE_COLS-1];

    initial begin
        for (int i=0; i<NUM_LINES; i++) begin
            for (int j=0; j<LINE_COLS; j++) begin
                mem[i][j] = 0;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (wr_en) begin
            mem[wr_line][wr_col] <= wr_data;
        end
    end

    // -------------------------------------------------------------------------
    //  Read: provide NUM_LINES outputs, oldest-line-first ordering
    //  rd_data[0] = newest (most recently written) line
    //  rd_data[NUM_LINES-1] = oldest buffered line
    // -------------------------------------------------------------------------
    genvar g;
    generate
        for (g = 0; g < NUM_LINES; g++) begin : gen_rd
            logic [$clog2(NUM_LINES)-1:0] slot;
            // slot rotates: newest line is at wr_line (just written to)
            // previous line is at (wr_line - 1) mod NUM_LINES, etc.
            assign slot = (wr_line + NUM_LINES - (g % NUM_LINES)) % NUM_LINES;
            
            // Forward wr_data if we are reading the line we are currently writing
            assign rd_data_flat[g*PIXEL_W +: PIXEL_W] = 
                (wr_en && (slot == wr_line) && (rd_col == wr_col)) ? wr_data : mem[slot][rd_col];
        end
    endgenerate

endmodule
