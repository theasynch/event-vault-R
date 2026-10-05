
module soc_system (
	clk_clk,
	hps_0_h2f_lw_axi_master_awid,
	hps_0_h2f_lw_axi_master_awaddr,
	hps_0_h2f_lw_axi_master_awlen,
	hps_0_h2f_lw_axi_master_awsize,
	hps_0_h2f_lw_axi_master_awburst,
	hps_0_h2f_lw_axi_master_awlock,
	hps_0_h2f_lw_axi_master_awcache,
	hps_0_h2f_lw_axi_master_awprot,
	hps_0_h2f_lw_axi_master_awvalid,
	hps_0_h2f_lw_axi_master_awready,
	hps_0_h2f_lw_axi_master_wid,
	hps_0_h2f_lw_axi_master_wdata,
	hps_0_h2f_lw_axi_master_wstrb,
	hps_0_h2f_lw_axi_master_wlast,
	hps_0_h2f_lw_axi_master_wvalid,
	hps_0_h2f_lw_axi_master_wready,
	hps_0_h2f_lw_axi_master_bid,
	hps_0_h2f_lw_axi_master_bresp,
	hps_0_h2f_lw_axi_master_bvalid,
	hps_0_h2f_lw_axi_master_bready,
	hps_0_h2f_lw_axi_master_arid,
	hps_0_h2f_lw_axi_master_araddr,
	hps_0_h2f_lw_axi_master_arlen,
	hps_0_h2f_lw_axi_master_arsize,
	hps_0_h2f_lw_axi_master_arburst,
	hps_0_h2f_lw_axi_master_arlock,
	hps_0_h2f_lw_axi_master_arcache,
	hps_0_h2f_lw_axi_master_arprot,
	hps_0_h2f_lw_axi_master_arvalid,
	hps_0_h2f_lw_axi_master_arready,
	hps_0_h2f_lw_axi_master_rid,
	hps_0_h2f_lw_axi_master_rdata,
	hps_0_h2f_lw_axi_master_rresp,
	hps_0_h2f_lw_axi_master_rlast,
	hps_0_h2f_lw_axi_master_rvalid,
	hps_0_h2f_lw_axi_master_rready,
	hps_io_hps_io_emac1_inst_TX_CLK,
	hps_io_hps_io_emac1_inst_TXD0,
	hps_io_hps_io_emac1_inst_TXD1,
	hps_io_hps_io_emac1_inst_TXD2,
	hps_io_hps_io_emac1_inst_TXD3,
	hps_io_hps_io_emac1_inst_RXD0,
	hps_io_hps_io_emac1_inst_MDIO,
	hps_io_hps_io_emac1_inst_MDC,
	hps_io_hps_io_emac1_inst_RX_CTL,
	hps_io_hps_io_emac1_inst_TX_CTL,
	hps_io_hps_io_emac1_inst_RX_CLK,
	hps_io_hps_io_emac1_inst_RXD1,
	hps_io_hps_io_emac1_inst_RXD2,
	hps_io_hps_io_emac1_inst_RXD3,
	hps_io_hps_io_sdio_inst_CMD,
	hps_io_hps_io_sdio_inst_D0,
	hps_io_hps_io_sdio_inst_D1,
	hps_io_hps_io_sdio_inst_CLK,
	hps_io_hps_io_sdio_inst_D2,
	hps_io_hps_io_sdio_inst_D3,
	hps_io_hps_io_usb1_inst_D0,
	hps_io_hps_io_usb1_inst_D1,
	hps_io_hps_io_usb1_inst_D2,
	hps_io_hps_io_usb1_inst_D3,
	hps_io_hps_io_usb1_inst_D4,
	hps_io_hps_io_usb1_inst_D5,
	hps_io_hps_io_usb1_inst_D6,
	hps_io_hps_io_usb1_inst_D7,
	hps_io_hps_io_usb1_inst_CLK,
	hps_io_hps_io_usb1_inst_STP,
	hps_io_hps_io_usb1_inst_DIR,
	hps_io_hps_io_usb1_inst_NXT,
	hps_io_hps_io_spim1_inst_SS1,
	hps_io_hps_io_spim1_inst_CLK,
	hps_io_hps_io_spim1_inst_MOSI,
	hps_io_hps_io_spim1_inst_MISO,
	hps_io_hps_io_spim1_inst_SS0,
	hps_io_hps_io_uart0_inst_RX,
	hps_io_hps_io_uart0_inst_TX,
	hps_io_hps_io_i2c1_inst_SDA,
	hps_io_hps_io_i2c1_inst_SCL,
	hps_io_hps_io_gpio_inst_GPIO53,
	memory_mem_a,
	memory_mem_ba,
	memory_mem_ck,
	memory_mem_ck_n,
	memory_mem_cke,
	memory_mem_cs_n,
	memory_mem_ras_n,
	memory_mem_cas_n,
	memory_mem_we_n,
	memory_mem_reset_n,
	memory_mem_dq,
	memory_mem_dqs,
	memory_mem_dqs_n,
	memory_mem_odt,
	memory_mem_dm,
	memory_oct_rzqin,
	reset_reset_n);	

	input		clk_clk;
	output	[11:0]	hps_0_h2f_lw_axi_master_awid;
	output	[20:0]	hps_0_h2f_lw_axi_master_awaddr;
	output	[3:0]	hps_0_h2f_lw_axi_master_awlen;
	output	[2:0]	hps_0_h2f_lw_axi_master_awsize;
	output	[1:0]	hps_0_h2f_lw_axi_master_awburst;
	output	[1:0]	hps_0_h2f_lw_axi_master_awlock;
	output	[3:0]	hps_0_h2f_lw_axi_master_awcache;
	output	[2:0]	hps_0_h2f_lw_axi_master_awprot;
	output		hps_0_h2f_lw_axi_master_awvalid;
	input		hps_0_h2f_lw_axi_master_awready;
	output	[11:0]	hps_0_h2f_lw_axi_master_wid;
	output	[31:0]	hps_0_h2f_lw_axi_master_wdata;
	output	[3:0]	hps_0_h2f_lw_axi_master_wstrb;
	output		hps_0_h2f_lw_axi_master_wlast;
	output		hps_0_h2f_lw_axi_master_wvalid;
	input		hps_0_h2f_lw_axi_master_wready;
	input	[11:0]	hps_0_h2f_lw_axi_master_bid;
	input	[1:0]	hps_0_h2f_lw_axi_master_bresp;
	input		hps_0_h2f_lw_axi_master_bvalid;
	output		hps_0_h2f_lw_axi_master_bready;
	output	[11:0]	hps_0_h2f_lw_axi_master_arid;
	output	[20:0]	hps_0_h2f_lw_axi_master_araddr;
	output	[3:0]	hps_0_h2f_lw_axi_master_arlen;
	output	[2:0]	hps_0_h2f_lw_axi_master_arsize;
	output	[1:0]	hps_0_h2f_lw_axi_master_arburst;
	output	[1:0]	hps_0_h2f_lw_axi_master_arlock;
	output	[3:0]	hps_0_h2f_lw_axi_master_arcache;
	output	[2:0]	hps_0_h2f_lw_axi_master_arprot;
	output		hps_0_h2f_lw_axi_master_arvalid;
	input		hps_0_h2f_lw_axi_master_arready;
	input	[11:0]	hps_0_h2f_lw_axi_master_rid;
	input	[31:0]	hps_0_h2f_lw_axi_master_rdata;
	input	[1:0]	hps_0_h2f_lw_axi_master_rresp;
	input		hps_0_h2f_lw_axi_master_rlast;
	input		hps_0_h2f_lw_axi_master_rvalid;
	output		hps_0_h2f_lw_axi_master_rready;
	output		hps_io_hps_io_emac1_inst_TX_CLK;
	output		hps_io_hps_io_emac1_inst_TXD0;
	output		hps_io_hps_io_emac1_inst_TXD1;
	output		hps_io_hps_io_emac1_inst_TXD2;
	output		hps_io_hps_io_emac1_inst_TXD3;
	input		hps_io_hps_io_emac1_inst_RXD0;
	inout		hps_io_hps_io_emac1_inst_MDIO;
	output		hps_io_hps_io_emac1_inst_MDC;
	input		hps_io_hps_io_emac1_inst_RX_CTL;
	output		hps_io_hps_io_emac1_inst_TX_CTL;
	input		hps_io_hps_io_emac1_inst_RX_CLK;
	input		hps_io_hps_io_emac1_inst_RXD1;
	input		hps_io_hps_io_emac1_inst_RXD2;
	input		hps_io_hps_io_emac1_inst_RXD3;
	inout		hps_io_hps_io_sdio_inst_CMD;
	inout		hps_io_hps_io_sdio_inst_D0;
	inout		hps_io_hps_io_sdio_inst_D1;
	output		hps_io_hps_io_sdio_inst_CLK;
	inout		hps_io_hps_io_sdio_inst_D2;
	inout		hps_io_hps_io_sdio_inst_D3;
	inout		hps_io_hps_io_usb1_inst_D0;
	inout		hps_io_hps_io_usb1_inst_D1;
	inout		hps_io_hps_io_usb1_inst_D2;
	inout		hps_io_hps_io_usb1_inst_D3;
	inout		hps_io_hps_io_usb1_inst_D4;
	inout		hps_io_hps_io_usb1_inst_D5;
	inout		hps_io_hps_io_usb1_inst_D6;
	inout		hps_io_hps_io_usb1_inst_D7;
	input		hps_io_hps_io_usb1_inst_CLK;
	output		hps_io_hps_io_usb1_inst_STP;
	input		hps_io_hps_io_usb1_inst_DIR;
	input		hps_io_hps_io_usb1_inst_NXT;
	output		hps_io_hps_io_spim1_inst_SS1;
	output		hps_io_hps_io_spim1_inst_CLK;
	output		hps_io_hps_io_spim1_inst_MOSI;
	input		hps_io_hps_io_spim1_inst_MISO;
	output		hps_io_hps_io_spim1_inst_SS0;
	input		hps_io_hps_io_uart0_inst_RX;
	output		hps_io_hps_io_uart0_inst_TX;
	inout		hps_io_hps_io_i2c1_inst_SDA;
	inout		hps_io_hps_io_i2c1_inst_SCL;
	inout		hps_io_hps_io_gpio_inst_GPIO53;
	output	[14:0]	memory_mem_a;
	output	[2:0]	memory_mem_ba;
	output		memory_mem_ck;
	output		memory_mem_ck_n;
	output		memory_mem_cke;
	output		memory_mem_cs_n;
	output		memory_mem_ras_n;
	output		memory_mem_cas_n;
	output		memory_mem_we_n;
	output		memory_mem_reset_n;
	inout	[31:0]	memory_mem_dq;
	inout	[3:0]	memory_mem_dqs;
	inout	[3:0]	memory_mem_dqs_n;
	output		memory_mem_odt;
	output	[3:0]	memory_mem_dm;
	input		memory_oct_rzqin;
	input		reset_reset_n;
endmodule
