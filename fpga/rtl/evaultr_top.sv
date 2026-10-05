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
    
    wire guardrail_valid;
    wire is_safe;
    // Offset 0x00: REG_CONTROL  (W)  — bit[0] = start, bit[1] = reset_accel
    // Offset 0x04: REG_PIXEL    (W)  — write a pixel (triggers s_axis_tvalid)
    // Offset 0x08: REG_FRAME_ID (W)  — current frame ID
    // Offset 0x0C: REG_EPS_F    (W)  — epsilon flux (Q15)
    // Offset 0x10: REG_EPS_X    (W)  — epsilon centroid (Q15)
    // Offset 0x14: REG_LAST     (W)  — bit[0] = last_col, bit[1] = last_row
    // Offset 0x00: REG_STATUS   (R)  — bit[0] = done, bit[1] = ready,
    //                                   bit[2] = guardrail_safe
    // Offset 0x04: REG_RESULT   (R)  — last L0 output value
    // Offset 0x08: REG_PERF_CNT (R)  — clock cycle counter (for timing)
    // =========================================================================
    logic [31:0] reg_control;
    logic [31:0] reg_status;
    logic [31:0] reg_frame_id;
    logic [31:0] reg_epsilon_f;
    logic [31:0] reg_epsilon_x;
    logic [31:0] reg_last_flags;

    // Pixel write -> AXI-Stream bridge
    reg          px_wr_pending;
    reg [31:0]   px_wr_data;
    reg          px_wr_last_col;
    reg          px_wr_last_row;

    // Hardware Traffic Generator (to measure max throughput without ARM bottleneck)
    reg [11:0] hw_gen_count;
    reg        hw_gen_active;

    // Performance counter (measures ONLY active processing cycles)
    reg [31:0]   perf_counter;
    reg          perf_running;
    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            perf_counter <= '0;
            perf_running <= 1'b0;
        end else begin
            if ((px_wr_pending || hw_gen_active) && !perf_running) begin
                perf_running <= 1'b1;
                perf_counter <= '0;
            end else if (guardrail_valid) begin // guardrail_valid is declared later, we'll use a wire
                perf_running <= 1'b0;
            end
            
            if (perf_running)
                perf_counter <= perf_counter + 1;
        end
    end

    // Capture last result for ARM readback
    reg [31:0]   last_result;

    // Simple AXI-Lite Write
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_control   <= '0;
            reg_frame_id  <= '0;
            reg_epsilon_f <= 32'd163;  // default 0.005 in Q15
            reg_epsilon_x <= 32'd3276; // default 0.1 in Q15
            reg_last_flags <= '0;
            s_axi_awready <= 1'b1;
            s_axi_wready  <= 1'b1;
            s_axi_bvalid  <= 1'b0;
            px_wr_pending <= 1'b0;
        end else begin
            // Clear single-cycle pixel write pulse
            if (px_wr_pending && s_axis_tready)
                px_wr_pending <= 1'b0;
                
            // HW Generator Logic
            if (reg_control[2]) begin
                hw_gen_active <= 1'b1;
                hw_gen_count <= '0;
                reg_control[2] <= 1'b0; // Auto-clear trigger
            end else if (hw_gen_active && dwt_in_ready) begin
                if (hw_gen_count == 4095)
                    hw_gen_active <= 1'b0;
                else
                    hw_gen_count <= hw_gen_count + 1;
            end

            if (s_axi_awvalid && s_axi_wvalid && s_axi_awready && s_axi_wready) begin
                s_axi_bvalid <= 1'b1;
                case (s_axi_awaddr[7:0])
                    8'h00: reg_control   <= s_axi_wdata;
                    8'h04: begin
                        // Pixel data write — push into the stream
                        px_wr_data     <= s_axi_wdata;
                        px_wr_last_col <= reg_last_flags[0];
                        px_wr_last_row <= reg_last_flags[1];
                        px_wr_pending  <= 1'b1;
                    end
                    8'h08: reg_frame_id  <= s_axi_wdata;
                    8'h0C: reg_epsilon_f <= s_axi_wdata;
                    8'h10: reg_epsilon_x <= s_axi_wdata;
                    8'h14: reg_last_flags <= s_axi_wdata;
                endcase
            end else if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end
        end
    end
    assign s_axi_bresp = 2'b00;

    // AXI-Lite Read — ARM reads status, results, and perf counter
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_axi_rvalid <= 1'b0;
            s_axi_rdata  <= '0;
        end else begin
            if (s_axi_arvalid && s_axi_arready) begin
                s_axi_rvalid <= 1'b1;
                case (s_axi_araddr[7:0])
                    8'h00: s_axi_rdata <= reg_status;
                    8'h04: s_axi_rdata <= last_result;
                    8'h08: s_axi_rdata <= perf_counter;
                    default: s_axi_rdata <= 32'hDEADBEEF;
                endcase
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end
    assign s_axi_arready = !s_axi_rvalid;
    assign s_axi_rresp   = 2'b00;



    // 1. 2D DWT Module
    wire dwt_out_valid;
    wire signed [31:0] dwt_out_L0;
    wire dwt_out_done;
    wire dwt_in_ready;

    // Mux between ARM MMIO and HW Traffic Generator
    // Mux between ARM MMIO and HW Traffic Generator
    wire [31:0] actual_in_data  = hw_gen_active ? {20'b0, hw_gen_count} : px_wr_data;
    wire        actual_in_valid = hw_gen_active ? 1'b1 : px_wr_pending;
    wire        actual_last_col = (hw_gen_active || hw_gen_count == 4095) ? (hw_gen_count[5:0] == 6'd63) : px_wr_last_col;
    wire        actual_last_row = (hw_gen_active || hw_gen_count == 4095) ? (hw_gen_count == 4095) : px_wr_last_row;
    
    assign s_axis_tready = dwt_in_ready;

    dwt_2d_top dwt_inst (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_rows(11'd64),
        .cfg_cols(11'd64),
        .in_valid(actual_in_valid),
        .in_data(actual_in_data),
        .in_last_col(actual_last_col),
        .in_last_row(actual_last_row),
        .in_ready(dwt_in_ready),
        .h3_valid(),
        .h3_LH(), .h3_HL(), .h3_HH(),
        .h2_valid(),
        .h2_LH(), .h2_HL(), .h2_HH(),
        .h1_valid(dwt_out_valid),
        .h1_LH(), .h1_HL(), .h1_HH(),
        .base_L0(dwt_out_L0),
        .done(dwt_out_done)
    );

    // Capture the last L0 result for ARM readback
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            last_result <= '0;
        else if (dwt_out_valid)
            last_result <= dwt_out_L0;
    end

    // 2. Science Guardrail Evaluator
    // Level 3 output is 8x8, so last_col happens every 8 valid pixels
    reg [2:0] l3_out_col_cnt;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            l3_out_col_cnt <= '0;
        else if (reg_control[2] || px_wr_pending) // clear on new frame
            l3_out_col_cnt <= '0;
        else if (dwt_out_valid)
            l3_out_col_cnt <= l3_out_col_cnt + 1;
    end
    wire l3_out_last_col = (l3_out_col_cnt == 3'd7);

    science_guardrail #(
        .PIXEL_W(32),
        .LINE_COLS(64)
    ) guardrail_inst (
        .clk(clk),
        .rst_n(rst_n),
        .in_valid(dwt_out_valid),
        .in_data(dwt_out_L0),
        .in_last_col(l3_out_last_col),
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

    // =========================================================================
    // Status Register (readable by ARM)
    // =========================================================================
    // bit[0] = DWT done flag (sticky)
    // bit[1] = DWT input ready
    // bit[2] = guardrail is_safe
    // bit[3] = guardrail decision_valid
    
    reg sticky_done;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            sticky_done <= 1'b0;
        else if (reg_control[2] || px_wr_pending) // clear on new hardware or software frame
            sticky_done <= 1'b0;
        else if (dwt_out_done)
            sticky_done <= 1'b1;
    end

    assign reg_status = {28'b0, guardrail_valid, is_safe, dwt_in_ready, sticky_done};

    // AXI-Stream Master output (directly from DWT L0)
    assign m_axis_tvalid = dwt_out_valid;
    assign m_axis_tdata  = dwt_out_L0;
    assign m_axis_tlast  = dwt_out_done;

endmodule

