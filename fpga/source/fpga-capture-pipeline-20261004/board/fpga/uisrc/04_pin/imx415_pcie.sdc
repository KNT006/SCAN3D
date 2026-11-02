## ============================================================
## SDC for IMX415 Camera + PCIe (PH1A90SEG324 migration)
## PH1A90SEG324-2, PCIe Gen2 x1
## Clock domains: sys_clk, sgdma_pll, ui_pll, PCIe, MIPI HS
## ============================================================

## 25MHz system clock (T16) ¡ª drives sgdma_pll only
create_clock -name sys_clk -period 40 -waveform {0 20} [get_ports {sys_clk}]

## MIPI HS clock: ~200MHz (DDR 400Mbps/lane for 4-lane 1080p30)
## This is the recovered clock from the MIPI CSI-2 clock lane
create_clock -name mipi_hs_clk -period 5.0 [get_ports {mipi_clk_hs_rx_p}]

## Let TD auto-derive all internal clocks (PLL outputs, etc.)
derive_clocks

## ============================================================
## Async clock groups
## 6 independent domains:
##   1. sgdma_pll outputs (core_clk 125MHz, app_auxclk 25MHz)
##   2. ui_pll outputs (cam_pclk 150MHz, cam_24m)
##      NOTE: clkc[1] (cam_100m) is reserved/unused, optimized out by TD
##   3. PCIe internal clocks (pcie_user_clk + core_clk from al_pcie_ip.sdc)
##   4. sys_clk (PLL input only)
##   5. MIPI HS clock (recovered from camera, fully async)
##   6. MIPI derived clocks (io_clk_div from HS clock)
## ============================================================

# Clock crossings are constrained individually in afc03_camera_cdc.sdc.
