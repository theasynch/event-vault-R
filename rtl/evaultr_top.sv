// =============================================================================
//  evaultr_top.sv — EventVault-R Master Integration Wrapper
//  EventVault-R Accelerator — Top Level
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Integrates all modules:
//    - Calibration Pipeline
//    - 2D Progressive DWT (3 levels)
//    - Source Extractor (L0)
//    - Science Guardrail Evaluator
//    - Escrow Controller (Metadata Manager)
//    - Resource Controller (Occupancy Monitor)
//    - Telemetry Downlink (UART simulation)
// =============================================================================

module evaultr_top #(
    parameter int PIXEL_W = 16,
    parameter int LINE_COLS = 1024
)(
    input  logic clk,
    input  logic rst_n,

    // Calibration inputs (From SDRAM or Sensor)
    input  logic                 start,
    input  logic                 pix_valid,
    input  logic [PIXEL_W-1:0]   pix_data,
    input  logic                 pix_last_col,
    input  logic                 pix_last_row,

    // Calibration BRAM write ports (dark + flat)
    input  logic                 dark_wr_en,
    input  logic [19:0]          dark_wr_addr,
    input  logic [PIXEL_W-1:0]   dark_wr_data,
    input  logic                 flat_wr_en,
    input  logic [19:0]          flat_wr_addr,
    input  logic [15:0]          flat_wr_data,

    // External Trigger Input
    input  logic                 ext_trigger,
    input  logic [31:0]          current_frame_id,
    input  logic [31:0]          current_timestamp,

    // Telemetry Output
    output logic                 telemetry_tx,

    // Control/Status outputs
    output logic                 done,
    output logic                 busy,
    output logic                 system_warning,
    output logic                 system_critical
);

    // =========================================================================
    // 1. Calibration Engine
    // =========================================================================
    logic                 cal_valid, cal_last_col, cal_last_row;
    logic [PIXEL_W-1:0]   cal_data;

    calibration_engine #(
        .PIXEL_W  (PIXEL_W),
        .FIXED_W  (32),
        .FRAC_W   (16),
        .MAX_COLS (LINE_COLS),
        .MAX_ROWS (1024)
    ) u_cal (
        .clk          (clk),
        .rst_n        (rst_n),
        .start        (start),
        .done         (done),
        .busy         (busy),
        .pix_valid    (pix_valid),
        .pix_data     (pix_data),
        .pix_last_col (pix_last_col),
        .pix_last_row (pix_last_row),
        .pix_ready    (), // Ignored, assuming streaming
        .dark_wr_en   (dark_wr_en),
        .dark_wr_addr (dark_wr_addr),
        .dark_wr_data (dark_wr_data),
        .flat_wr_en   (flat_wr_en),
        .flat_wr_addr (flat_wr_addr),
        .flat_wr_data (flat_wr_data),
        .cal_valid    (cal_valid),
        .cal_data     (cal_data),
        .cal_last_col (cal_last_col),
        .cal_last_row (cal_last_row)
    );

    // =========================================================================
    // 2. 2D Progressive DWT (3 Levels)
    // =========================================================================
    logic             l1_valid;
    logic [PIXEL_W:0] l1_LH, l1_HL, l1_HH;

    logic               l2_valid;
    logic [PIXEL_W+1:0] l2_LH, l2_HL, l2_HH;

    logic               l3_valid;
    logic [PIXEL_W+2:0] l3_LH, l3_HL, l3_HH;
    logic [PIXEL_W+2:0] base_L0;

    dwt_2d_top #(
        .IN_W(PIXEL_W),
        .LINE_COLS(LINE_COLS)
    ) u_dwt_2d (
        .clk         (clk),
        .rst_n       (rst_n),
        .in_valid    (cal_valid),
        .in_data     (cal_data),
        .in_last_col (cal_last_col),
        .in_last_row (cal_last_row),

        .l1_valid    (l1_valid),
        .l1_LH       (l1_LH), .l1_HL(l1_HL), .l1_HH(l1_HH),
        
        .l2_valid    (l2_valid),
        .l2_LH       (l2_LH), .l2_HL(l2_HL), .l2_HH(l2_HH),
        
        .l3_valid    (l3_valid),
        .l3_LH       (l3_LH), .l3_HL(l3_HL), .l3_HH(l3_HH),
        .base_L0     (base_L0),
        
        .done        () // Tracked by calibration or internal FSM
    );

    // =========================================================================
    // 3. Source Extraction (on L0 Base Layer)
    // =========================================================================
    logic               source_valid;
    logic [9:0]         source_x;
    logic [9:0]         source_y;
    logic [PIXEL_W+2:0] source_flux;
    
    // Configurable threshold (hardcoded for now)
    logic [PIXEL_W+2:0] detect_threshold;
    assign detect_threshold = 19'd500; 

    source_extractor #(
        .PIXEL_W(PIXEL_W + 3), 
        .LINE_COLS(LINE_COLS / 8) // L0 is 1/8th size
    ) u_extractor (
        .clk          (clk),
        .rst_n        (rst_n),
        .threshold    (detect_threshold),
        
        .in_valid     (l3_valid),
        .in_data      (base_L0),
        .in_last_col  (1'b0), // Simplification: we'd track last_col from DWT L3
        .in_last_row  (1'b0),
        
        .source_valid (source_valid),
        .source_x     (source_x),
        .source_y     (source_y),
        .source_flux  (source_flux)
    );

    // =========================================================================
    // 4. Science Guardrail Evaluator
    // =========================================================================
    logic guardrail_decision_valid;
    logic guardrail_is_safe;

    // We feed the reconstructed pixels into the guardrail.
    // For this prototype wrapper, we wire L0 as the "reconstructed" stream just to 
    // show the connectivity. In a full system, an IDWT output goes here.
    science_guardrail #(
        .PIXEL_W(PIXEL_W + 3),
        .LINE_COLS(LINE_COLS / 8)
    ) u_guardrail (
        .clk            (clk),
        .rst_n          (rst_n),
        
        .in_valid       (l3_valid),
        .in_data        (base_L0),
        .in_last_col    (1'b0),
        .in_last_row    (1'b0),
        
        .check_en       (source_valid),
        .ref_x          (source_x),
        .ref_y          (source_y),
        .ref_flux       ({13'd0, source_flux}), // Extended to 32-bit
        .eps_flux_q15   (16'd163),  // 0.005
        .eps_cent_q15   (16'd3276), // 0.1
        
        .decision_valid (guardrail_decision_valid),
        .is_safe        (guardrail_is_safe)
    );

    // =========================================================================
    // 5. Escrow Controller (Circular Buffer Metadata)
    // =========================================================================
    logic [7:0]  escrow_occupancy;
    logic        escrow_full;
    logic        uncontrolled_loss;
    
    // For demonstration, pushing a frame ID whenever the pipeline finishes a frame
    // In reality, this is orchestrated by a central FSM
    logic push_req_pulse;
    always_ff @(posedge clk) push_req_pulse <= (done && !busy);

    escrow_controller #(
        .CAPACITY(128)
    ) u_escrow (
        .clk               (clk),
        .rst_n             (rst_n),
        .occupancy         (escrow_occupancy),
        .is_full           (escrow_full),
        .uncontrolled_loss (uncontrolled_loss),
        
        .push_req          (push_req_pulse),
        .push_frame_id     (current_frame_id),
        .push_timestamp    (current_timestamp),
        .push_ack          (),
        .push_sdram_addr   (),
        
        .lock_req          (guardrail_decision_valid && !guardrail_is_safe),
        .lock_frame_id     (current_frame_id),
        .lock_ack          (),
        
        .prom_req          (ext_trigger),
        .prom_frame_id     (current_frame_id),
        .prom_ack          ()
    );

    // =========================================================================
    // 6. Resource Controller
    // =========================================================================
    logic force_purge_req;
    
    resource_controller #(
        .CAPACITY(128)
    ) u_resource (
        .clk             (clk),
        .rst_n           (rst_n),
        .occupancy       (escrow_occupancy),
        .warning_mode    (system_warning),
        .critical_mode   (system_critical),
        .force_purge_req (force_purge_req)
    );

    // =========================================================================
    // 7. Telemetry Downlink TX
    // =========================================================================
    // Simulating downlink queue of base_L0 bytes
    logic tx_ready;
    
    downlink_tx #(
        .CLK_FREQ_MHZ (100),
        .BAUD_RATE_BPS(9600)
    ) u_telemetry (
        .clk      (clk),
        .rst_n    (rst_n),
        .tx_req   (l3_valid && tx_ready), 
        .tx_data  (base_L0[7:0]), // Downlinking lower byte for demo
        .tx_ready (tx_ready),
        .tx_out   (telemetry_tx)
    );

endmodule
