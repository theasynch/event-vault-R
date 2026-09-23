# 50MHz Board Clock
create_clock -name "clk" -period 20.000 [get_ports {clk}]

# Derive PLL clocks (if any are used in the future)
derive_pll_clocks

# Derive clock uncertainty
derive_clock_uncertainty
