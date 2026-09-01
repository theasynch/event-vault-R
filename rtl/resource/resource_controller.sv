// =============================================================================
//  resource_controller.sv — Resource and Occupancy Monitor
//  EventVault-R Accelerator — Resource Module
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Monitors the escrow buffer occupancy and transitions between modes:
//  - NOMINAL: occupancy < 70%
//  - WARNING: occupancy >= 70%
//  - CRITICAL: occupancy >= 90%
// =============================================================================

module resource_controller #(
    parameter int CAPACITY = 128
)(
    input  logic         clk,
    input  logic         rst_n,

    // Input from escrow controller
    input  logic [7:0]   occupancy,

    // Outputs
    output logic         warning_mode,
    output logic         critical_mode,
    output logic         force_purge_req
);

    localparam int THRESH_WARNING  = (CAPACITY * 7) / 10;
    localparam int THRESH_CRITICAL = (CAPACITY * 9) / 10;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            warning_mode    <= 1'b0;
            critical_mode   <= 1'b0;
            force_purge_req <= 1'b0;
        end else begin
            if (occupancy >= THRESH_CRITICAL) begin
                warning_mode    <= 1'b1;
                critical_mode   <= 1'b1;
                force_purge_req <= 1'b1; // Signal pipeline to drop unneeded layers
            end else if (occupancy >= THRESH_WARNING) begin
                warning_mode    <= 1'b1;
                critical_mode   <= 1'b0;
                force_purge_req <= 1'b0;
            end else begin
                warning_mode    <= 1'b0;
                critical_mode   <= 1'b0;
                force_purge_req <= 1'b0;
            end
        end
    end

endmodule
