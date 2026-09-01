// =============================================================================
//  escrow_controller.sv — Circular Escrow Buffer Metadata Manager
//  EventVault-R Accelerator — Escrow Module
//  Target: Intel Cyclone V / Xilinx 7-Series
//
//  Manages the circular buffer metadata for up to 128 frames.
//  Uses an internal BRAM table.
//  Functions:
//   - PUSH: Allocate a new entry. If full, evict the oldest unlocked entry.
//   - LOCK: Set the lock bit for a specific frame_id.
//   - PROMOTE: Set the promoted bit for a specific frame_id.
// =============================================================================

module escrow_controller #(
    parameter int CAPACITY = 128
)(
    input  logic         clk,
    input  logic         rst_n,

    // Status
    output logic [7:0]   occupancy,
    output logic         is_full,
    output logic         uncontrolled_loss, // Pulses if eviction fails

    // PUSH interface
    input  logic         push_req,
    input  logic [31:0]  push_frame_id,
    input  logic [31:0]  push_timestamp,
    output logic         push_ack,
    output logic [31:0]  push_sdram_addr,   // Allocated memory location

    // LOCK interface
    input  logic         lock_req,
    input  logic [31:0]  lock_frame_id,
    output logic         lock_ack,

    // PROMOTE interface
    input  logic         prom_req,
    input  logic [31:0]  prom_frame_id,
    output logic         prom_ack
);

    localparam int PTR_W = $clog2(CAPACITY);

    // -------------------------------------------------------------------------
    // Metadata BRAM Table
    // -------------------------------------------------------------------------
    typedef struct packed {
        logic [31:0] frame_id;
        logic [31:0] timestamp;
        logic        locked;
        logic        promoted;
        logic        valid;
    } entry_t;

    entry_t meta_mem [0:CAPACITY-1];

    // Read/Write ports for FSM
    logic [PTR_W-1:0] mem_addr;
    logic             mem_we;
    entry_t           mem_din;
    entry_t           mem_dout;

    always_ff @(posedge clk) begin
        if (mem_we)
            meta_mem[mem_addr] <= mem_din;
        mem_dout <= meta_mem[mem_addr];
    end

    // -------------------------------------------------------------------------
    // FSM Variables
    // -------------------------------------------------------------------------
    typedef enum logic [3:0] {
        IDLE,
        // Push States
        PUSH_CHECK_FULL,
        PUSH_FIND_EVICT,
        PUSH_WRITE,
        // Search States (used by Lock and Promote)
        SEARCH_START,
        SEARCH_READ,
        SEARCH_CHECK,
        SEARCH_UPDATE
    } state_t;

    state_t state, next_state;

    logic [PTR_W-1:0] head_ptr; // Points to next empty/overwrite slot
    logic [PTR_W-1:0] tail_ptr; // Points to oldest slot (for eviction)
    logic [PTR_W-1:0] search_ptr;
    logic [PTR_W-1:0] search_count;
    
    logic [7:0]       count;

    assign occupancy = count;
    assign is_full   = (count == CAPACITY);

    // Operation latches
    logic op_is_lock; // 1 = lock, 0 = promote
    logic [31:0] target_frame_id;

    // -------------------------------------------------------------------------
    // FSM Logic
    // -------------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            head_ptr <= '0;
            tail_ptr <= '0;
            count <= '0;
            
            push_ack <= 1'b0;
            lock_ack <= 1'b0;
            prom_ack <= 1'b0;
            uncontrolled_loss <= 1'b0;
            
            mem_we <= 1'b0;
        end else begin
            // Default outputs
            push_ack <= 1'b0;
            lock_ack <= 1'b0;
            prom_ack <= 1'b0;
            uncontrolled_loss <= 1'b0;
            mem_we <= 1'b0;

            case (state)
                IDLE: begin
                    if (push_req) begin
                        state <= PUSH_CHECK_FULL;
                    end else if (lock_req) begin
                        op_is_lock <= 1'b1;
                        target_frame_id <= lock_frame_id;
                        state <= SEARCH_START;
                    end else if (prom_req) begin
                        op_is_lock <= 1'b0;
                        target_frame_id <= prom_frame_id;
                        state <= SEARCH_START;
                    end
                end

                // --- PUSH SEQUENCE ---
                PUSH_CHECK_FULL: begin
                    if (is_full) begin
                        // Need to find eviction victim starting from tail
                        search_ptr <= tail_ptr;
                        search_count <= '0;
                        mem_addr <= tail_ptr;
                        state <= PUSH_FIND_EVICT;
                    end else begin
                        // Not full, use head
                        mem_addr <= head_ptr;
                        state <= PUSH_WRITE;
                    end
                end

                PUSH_FIND_EVICT: begin
                    // Read takes 1 cycle. We check mem_dout.
                    // This is a simplified 2-cycle loop per entry.
                    // Cycle 1: address set, wait for dout
                    // Cycle 2: check dout
                    if (search_count > 0 && 
                        mem_dout.valid && 
                        !mem_dout.locked && 
                        !mem_dout.promoted) 
                    begin
                        // Found victim
                        head_ptr <= search_ptr; // Overwrite here
                        mem_addr <= search_ptr;
                        tail_ptr <= (search_ptr == CAPACITY-1) ? '0 : search_ptr + 1'b1;
                        state <= PUSH_WRITE;
                        count <= count - 1'b1; // Will be +1 in WRITE
                    end else if (search_count == CAPACITY) begin
                        // Wrapped around, everything locked!
                        uncontrolled_loss <= 1'b1;
                        push_ack <= 1'b1; // Fail graceful
                        state <= IDLE;
                    end else begin
                        // Keep searching
                        search_ptr <= (search_ptr == CAPACITY-1) ? '0 : search_ptr + 1'b1;
                        mem_addr <= (search_ptr == CAPACITY-1) ? '0 : search_ptr + 1'b1;
                        search_count <= search_count + 1'b1;
                    end
                end

                PUSH_WRITE: begin
                    mem_we <= 1'b1;
                    mem_din.frame_id  <= push_frame_id;
                    mem_din.timestamp <= push_timestamp;
                    mem_din.locked    <= 1'b0;
                    mem_din.promoted  <= 1'b0;
                    mem_din.valid     <= 1'b1;
                    
                    // Memory location calculation (simple fixed offset mapping)
                    // SDRAM base + (head_ptr * ENTRY_SIZE)
                    // Assume 1MB per frame: 0x100000 bytes
                    push_sdram_addr <= head_ptr * 32'h00100000;
                    
                    head_ptr <= (head_ptr == CAPACITY-1) ? '0 : head_ptr + 1'b1;
                    count <= count + 1'b1;
                    
                    push_ack <= 1'b1;
                    state <= IDLE;
                end

                // --- SEARCH SEQUENCE (LOCK/PROMOTE) ---
                SEARCH_START: begin
                    search_ptr <= '0;
                    search_count <= '0;
                    mem_addr <= '0;
                    state <= SEARCH_READ;
                end

                SEARCH_READ: begin
                    state <= SEARCH_CHECK;
                end

                SEARCH_CHECK: begin
                    if (mem_dout.valid && mem_dout.frame_id == target_frame_id) begin
                        // Found it!
                        state <= SEARCH_UPDATE;
                    end else if (search_count == CAPACITY-1) begin
                        // Not found
                        if (op_is_lock) lock_ack <= 1'b1;
                        else prom_ack <= 1'b1;
                        state <= IDLE;
                    end else begin
                        search_ptr <= search_ptr + 1'b1;
                        mem_addr <= search_ptr + 1'b1;
                        search_count <= search_count + 1'b1;
                        state <= SEARCH_READ;
                    end
                end

                SEARCH_UPDATE: begin
                    mem_we <= 1'b1;
                    mem_addr <= search_ptr;
                    mem_din <= mem_dout;
                    if (op_is_lock) mem_din.locked <= 1'b1;
                    else mem_din.promoted <= 1'b1;

                    if (op_is_lock) lock_ack <= 1'b1;
                    else prom_ack <= 1'b1;
                    state <= IDLE;
                end

            endcase
        end
    end

endmodule
