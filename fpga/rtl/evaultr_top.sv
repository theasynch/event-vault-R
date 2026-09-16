// =============================================================================
//  evaultr_top.sv — EventVault-R Master Integration Wrapper
//  EventVault-R Accelerator — Top Level (Quartus / DE1-SoC)
//
//  Integrates FPGA-accelerated data path modules:
//    - 2D Progressive DWT (3 levels, bior4.4/db4)
//    - Science Guardrail Evaluator
//
//  Interfaces:
//    - AXI4-Lite (Slave)  : Control and Status Registers from ARM HPS
//    - AXI4-Stream (Slave): Pixel data in from ARM HPS (or DMA)
//    - AXI4-Stream (Master): Processed telemetry/residuals out to ARM HPS
// =============================================================================

module evaultr_top #(
    parameter int PIXEL_W = 16,
    parameter int AXI_ADDR_W = 12,
    parameter int AXI_DATA_W = 32
)(
    input  logic clk,
    input  logic rst_n,

    // ---------------------------------------------------------
    // AXI4-Lite Slave Interface (Control Plane)
    // ---------------------------------------------------------
    input  logic [AXI_ADDR_W-1:0] s_axi_awaddr,
    input  logic                  s_axi_awvalid,
    output logic                  s_axi_awready,
    input  logic [AXI_DATA_W-1:0] s_axi_wdata,
    input  logic [3:0]            s_axi_wstrb,
    input  logic                  s_axi_wvalid,
    output logic                  s_axi_wready,
    output logic [1:0]            s_axi_bresp,
    output logic                  s_axi_bvalid,
    input  logic                  s_axi_bready,
    input  logic [AXI_ADDR_W-1:0] s_axi_araddr,
    input  logic                  s_axi_arvalid,
    output logic                  s_axi_arready,
    output logic [AXI_DATA_W-1:0] s_axi_rdata,
    output logic [1:0]            s_axi_rresp,
    output logic                  s_axi_rvalid,
    input  logic                  s_axi_rready,

    // ---------------------------------------------------------
    // AXI4-Stream Slave Interface (Data In)
    // ---------------------------------------------------------
    input  logic [31:0]           s_axis_tdata,
    input  logic                  s_axis_tvalid,
    input  logic                  s_axis_tlast,
    output logic                  s_axis_tready,

    // ---------------------------------------------------------
    // AXI4-Stream Master Interface (Data Out)
    // ---------------------------------------------------------
    output logic [31:0]           m_axis_tdata,
    output logic                  m_axis_tvalid,
    output logic                  m_axis_tlast,
    input  logic                  m_axis_tready
);

    // =========================================================================
    // Register Map / Control Logic
    // =========================================================================
    logic [31:0] reg_control;
    logic [31:0] reg_status;
    logic [31:0] reg_frame_id;
    logic [31:0] reg_epsilon_f;
    logic [31:0] reg_epsilon_x;

    // Simple AXI-Lite Write
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_control <= '0;
            reg_frame_id <= '0;
            reg_epsilon_f <= 32'd163;  // default 0.005 in Q15
            reg_epsilon_x <= 32'd3276; // default 0.1 in Q15
            s_axi_awready <= 1'b1;
            s_axi_wready  <= 1'b1;
            s_axi_bvalid  <= 1'b0;
        end else begin
            if (s_axi_awvalid && s_axi_wvalid && s_axi_awready && s_axi_wready) begin
                s_axi_bvalid <= 1'b1;
                // Simplified decoding for prototype
                case (s_axi_awaddr[7:0])
                    8'h00: reg_control <= s_axi_wdata;
                    8'h08: reg_frame_id <= s_axi_wdata;
                    8'h0C: reg_epsilon_f <= s_axi_wdata;
                    8'h10: reg_epsilon_x <= s_axi_wdata;
                endcase
            end else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end
        end
    end
    assign s_axi_bresp = 2'b00;

    // AXI-Lite Read (Stubbed)
    assign s_axi_arready = 1'b1;
    assign s_axi_rvalid  = s_axi_arvalid;
    assign s_axi_rdata   = 32'hDEADBEEF;
    assign s_axi_rresp   = 2'b00;

    // =========================================================================
    // DWT and Guardrail IPs (Placeholders for instantiation)
    // =========================================================================
    // In Phase C, these modules will consume s_axis and produce m_axis.
    
    // 1. 2D DWT Module
    wire dwt_out_valid;
    wire signed [31:0] dwt_out_L0;
    wire dwt_out_done;
    
    // Extract AXI-Stream signals
    wire in_last_col = s_axis_tlast; // Simplified mapping for now
    wire in_last_row = s_axis_tlast; // Needs properly generated last_row

    dwt_2d_top dwt_inst (
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(s_axis_tvalid),
        .in_data(s_axis_tdata),
        .in_last_col(in_last_col),
        .in_last_row(in_last_row),
        .in_ready(s_axis_tready),
        .l0_valid(dwt_out_valid),
        .l0_data(dwt_out_L0),
        .l0_done(dwt_out_done)
    );

    // 2. Science Guardrail Evaluator
    wire guardrail_valid;
    wire is_safe;

    science_guardrail #(
        .PIXEL_W(32),
        .LINE_COLS(64)
    ) guardrail_inst (
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(dwt_out_valid),
        .in_data(dwt_out_L0),
        .in_last_col(1'b0), // Not fully used for evaluating bounds unless specifically tracked
        .in_last_row(dwt_out_done),
        .check_en(1'b1),
        .ref_x(10'd0),
        .ref_y(10'd0),
        .ref_flux(32'd0),
        .eps_flux_q15(reg_epsilon_f[15:0]),
        .eps_cent_q15(reg_epsilon_x[15:0]),
        .decision_valid(guardrail_valid),
        .is_safe(is_safe)
    );

    // Update AXI-Stream Master Interface to output DWT L0 data for now
    // We append the guardrail safe status to the highest bit (or similar).
    // Let's just output L0 data directly.
    assign m_axis_tvalid = dwt_out_valid;
    assign m_axis_tdata  = dwt_out_L0;
    assign m_axis_tlast  = dwt_out_done;

endmodule
