// =============================================================================
//  downlink_tx.sv — Telemetry Downlink Queue Manager
//  EventVault-R Accelerator — Telemetry Module
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Simulates a slow telemetry downlink.
//  Accepts L0 base layers and promoted H layers via an input FIFO.
//  Streams them out byte-by-byte at a configurable rate (simulating Mbps).
// =============================================================================

module downlink_tx #(
    parameter int CLK_FREQ_MHZ  = 100,
    parameter int BAUD_RATE_BPS = 9600 // Very slow for simulation
)(
    input  logic         clk,
    input  logic         rst_n,

    // Input FIFO interface (from SDRAM or direct)
    input  logic         tx_req,
    input  logic [7:0]   tx_data,
    output logic         tx_ready, // High when not busy

    // Serial TX (UART-like, simplified)
    output logic         tx_out
);

    // Calculate clock divider for baud rate
    localparam int BAUD_DIV = (CLK_FREQ_MHZ * 1000000) / BAUD_RATE_BPS;

    logic [31:0] baud_cnt;
    logic        baud_tick;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            baud_cnt <= '0;
            baud_tick <= 1'b0;
        end else begin
            if (baud_cnt == BAUD_DIV - 1) begin
                baud_cnt <= '0;
                baud_tick <= 1'b1;
            end else begin
                baud_cnt <= baud_cnt + 1'b1;
                baud_tick <= 1'b0;
            end
        end
    end

    // -------------------------------------------------------------------------
    // UART TX State Machine
    // -------------------------------------------------------------------------
    typedef enum logic [1:0] {
        IDLE,
        START,
        DATA,
        STOP
    } state_t;

    state_t state;
    logic [7:0] shift_reg;
    logic [2:0] bit_idx;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state    <= IDLE;
            tx_ready <= 1'b1;
            tx_out   <= 1'b1; // Idle high
            bit_idx  <= '0;
            shift_reg <= '0;
        end else begin
            case (state)
                IDLE: begin
                    tx_ready <= 1'b1;
                    tx_out   <= 1'b1;
                    if (tx_req) begin
                        shift_reg <= tx_data;
                        tx_ready  <= 1'b0;
                        state     <= START;
                        // Synchronize to next baud tick by not doing anything yet
                    end
                end

                START: begin
                    if (baud_tick) begin
                        tx_out <= 1'b0; // Start bit
                        state  <= DATA;
                        bit_idx <= '0;
                    end
                end

                DATA: begin
                    if (baud_tick) begin
                        tx_out <= shift_reg[0];
                        shift_reg <= {1'b0, shift_reg[7:1]};
                        if (bit_idx == 7) begin
                            state <= STOP;
                        end else begin
                            bit_idx <= bit_idx + 1'b1;
                        end
                    end
                end

                STOP: begin
                    if (baud_tick) begin
                        tx_out <= 1'b1; // Stop bit
                        state  <= IDLE; // Back to IDLE, tx_ready goes high next cycle
                    end
                end
            endcase
        end
    end

endmodule
