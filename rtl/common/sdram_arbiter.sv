// =============================================================================
//  sdram_arbiter.sv — Simple Round-Robin SDRAM Access Arbiter
//  EventVault-R Accelerator — Common Library
//  Target: Intel Cyclone V (DE1-SoC) — interfaces to Altera SDRAM Controller IP
//
//  The DE1-SoC FPGA-side SDRAM (IS42S32200L, 64 MB, 32-bit × 166 MHz) is
//  shared between all accelerator modules. This arbiter provides NUM_PORTS
//  Avalon-MM master interfaces and serialises them onto the single SDRAM
//  controller Avalon-MM slave port using round-robin priority.
//
//  Port interface (each master):
//    addr   [31:0]  — byte address (must be 4-byte aligned)
//    burstcount [7:0] — number of 32-bit words
//    wr_en         — write request
//    wr_data[31:0] — write data
//    rd_en         — read request
//    rd_data[31:0] — read data (from SDRAM controller)
//    rd_valid      — read data valid
//    wait_req      — backpressure from arbiter
// =============================================================================

module sdram_arbiter #(
    parameter int NUM_PORTS = 4,        // number of client masters
    parameter int ADDR_W    = 32,
    parameter int DATA_W    = 32,
    parameter int BURST_W   = 8
)(
    input  logic                  clk,
    input  logic                  rst_n,

    // ---- Client master ports ------------------------------------------------
    input  logic [ADDR_W-1:0]     m_addr      [0:NUM_PORTS-1],
    input  logic [BURST_W-1:0]    m_burstcount [0:NUM_PORTS-1],
    input  logic                  m_wr_en     [0:NUM_PORTS-1],
    input  logic [DATA_W-1:0]     m_wr_data   [0:NUM_PORTS-1],
    input  logic                  m_rd_en     [0:NUM_PORTS-1],
    output logic [DATA_W-1:0]     m_rd_data   [0:NUM_PORTS-1],
    output logic                  m_rd_valid  [0:NUM_PORTS-1],
    output logic                  m_wait_req  [0:NUM_PORTS-1],

    // ---- SDRAM Controller Avalon-MM slave port ------------------------------
    output logic [ADDR_W-1:0]     s_addr,
    output logic [BURST_W-1:0]    s_burstcount,
    output logic                  s_wr_en,
    output logic [DATA_W-1:0]     s_wr_data,
    output logic                  s_rd_en,
    input  logic [DATA_W-1:0]     s_rd_data,
    input  logic                  s_rd_valid,
    input  logic                  s_wait_req
);

    // -------------------------------------------------------------------------
    //  Round-robin grant FSM
    // -------------------------------------------------------------------------
    logic [$clog2(NUM_PORTS)-1:0] grant;        // current owner
    logic                         burst_active;  // prevents mid-burst preemption
    logic [BURST_W-1:0]           burst_cnt;

    // Determine next grant (round-robin, skip idle ports)
    function automatic logic [$clog2(NUM_PORTS)-1:0] next_grant(
        input logic [$clog2(NUM_PORTS)-1:0] cur,
        input logic [NUM_PORTS-1:0]         req
    );
        logic [$clog2(NUM_PORTS)-1:0] n;
        n = cur;
        for (int i = 0; i < NUM_PORTS; i++) begin
            n = (n == NUM_PORTS - 1) ? '0 : n + 1'b1;
            if (req[n]) return n;
        end
        return cur; // no requests — stay
    endfunction

    logic [NUM_PORTS-1:0] any_req;
    genvar g;
    generate
        for (g = 0; g < NUM_PORTS; g++)
            assign any_req[g] = m_rd_en[g] | m_wr_en[g];
    endgenerate

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grant        <= '0;
            burst_active <= 1'b0;
            burst_cnt    <= '0;
        end else begin
            if (!burst_active) begin
                if (any_req != '0)
                    grant <= next_grant(grant, any_req);
            end else begin
                // Track burst completion (count down read beats)
                if (s_rd_valid) begin
                    if (burst_cnt == 1)
                        burst_active <= 1'b0;
                    else
                        burst_cnt <= burst_cnt - 1'b1;
                end
            end

            // Latch burst length on new rd request
            if (!burst_active && m_rd_en[grant] && !s_wait_req) begin
                burst_active <= 1'b1;
                burst_cnt    <= m_burstcount[grant];
            end
        end
    end

    // -------------------------------------------------------------------------
    //  Mux: connect granted port to SDRAM controller
    // -------------------------------------------------------------------------
    assign s_addr       = m_addr      [grant];
    assign s_burstcount = m_burstcount[grant];
    assign s_wr_en      = m_wr_en     [grant];
    assign s_wr_data    = m_wr_data   [grant];
    assign s_rd_en      = m_rd_en     [grant];

    // Demux read data back to the granted port only
    always_comb begin
        for (int i = 0; i < NUM_PORTS; i++) begin
            m_rd_data [i] = s_rd_data;
            m_rd_valid[i] = (i == int'(grant)) ? s_rd_valid : 1'b0;
            m_wait_req[i] = (i == int'(grant)) ? s_wait_req : 1'b1;
        end
    end

endmodule
