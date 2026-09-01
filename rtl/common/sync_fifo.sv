// =============================================================================
//  sync_fifo.sv — Synchronous FIFO (First Word Fall Through)
//  EventVault-R Accelerator — Common Library
//  Target: Intel Cyclone V (DE1-SoC, 5CSEMA5F31C6)
//
//  Synthesis: Infers M10K BRAM when DEPTH >= 64
//  Parameters:
//    DATA_W : data width in bits
//    DEPTH  : number of entries (must be power of 2)
// =============================================================================

module sync_fifo #(
    parameter int DATA_W = 16,
    parameter int DEPTH  = 256,
    localparam int PTR_W = $clog2(DEPTH)
)(
    input  logic              clk,
    input  logic              rst_n,

    // Write port
    input  logic              wr_en,
    input  logic [DATA_W-1:0] wr_data,
    output logic              full,

    // Read port (FWFT: data appears at rd_data the same cycle it is valid)
    input  logic              rd_en,
    output logic [DATA_W-1:0] rd_data,
    output logic              empty,

    // Status
    output logic [PTR_W:0]    count      // number of entries currently stored
);

    // -------------------------------------------------------------------------
    //  Memory array (synthesizes to M10K BRAM on Cyclone V)
    // -------------------------------------------------------------------------
    logic [DATA_W-1:0] mem [0:DEPTH-1];

    // -------------------------------------------------------------------------
    //  Read / Write pointers (one extra bit for full/empty discrimination)
    // -------------------------------------------------------------------------
    logic [PTR_W:0] wr_ptr;   // write pointer (PTR_W+1 bits)
    logic [PTR_W:0] rd_ptr;   // read  pointer (PTR_W+1 bits)

    assign count = wr_ptr - rd_ptr;
    assign full  = (count == PTR_W'(DEPTH));
    assign empty = (count == '0);

    // -------------------------------------------------------------------------
    //  Write logic
    // -------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
        end else if (wr_en && !full) begin
            mem[wr_ptr[PTR_W-1:0]] <= wr_data;
            wr_ptr                  <= wr_ptr + 1'b1;
        end
    end

    // -------------------------------------------------------------------------
    //  Read logic (FWFT — rd_data is combinatorially driven from mem)
    // -------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            rd_ptr <= '0;
        else if (rd_en && !empty)
            rd_ptr <= rd_ptr + 1'b1;
    end

    assign rd_data = mem[rd_ptr[PTR_W-1:0]];   // FWFT: immediate read

endmodule
