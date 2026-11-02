`timescale 1ns/1ps
// NEW component target with reset-locked AXI ownership; derived from BIST top.
// Existing afc03_ddr_bist_top and production board sources are not modified.
// Control/debug/external AXI ports use dfi_clk_out.
// NOT a board-download top: no GPIO pin assignment for test control/debug.
// Next integration must add a host command mailbox and coherent status snapshot.
module afc03_ddr_axi_port_top #(parameter ADD_REF_BUFG=1, parameter BIST_WORDS=4096, parameter BIST_TIMEOUT=100000000) (
    input wire ref_clk_100m, reset_n,
    input wire bist_start,
    // All ownership/AXI/control ports below use dfi_clk_out, no implicit CDC.
    input wire select_valid,output wire select_ready,input wire [1:0] select_owner,
    output wire select_result_valid,input wire select_result_ready,
    output wire select_result_ok,output wire [3:0] select_result_error,
    output wire [1:0] owner,
    output wire external_enabled,external_reset_n,
    output wire bist_busy,bist_done,bist_passed,output wire [3:0] bist_fault,
    output reg bist_start_rejected,
    output wire [4:0] response_faults,
    output wire [3:0] last_bid,last_rid,
    output wire [1:0] last_bresp,last_rresp,
    input wire [4-1:0] ext_awid,
    input wire [27:0] ext_awaddr,
    input wire [8-1:0] ext_awlen,
    input wire [3-1:0] ext_awsize,
    input wire [2-1:0] ext_awburst,
    input wire  ext_awvalid,
    input wire [128-1:0] ext_wdata,
    input wire [16-1:0] ext_wstrb,
    input wire  ext_wlast,
    input wire  ext_wvalid,
    input wire  ext_bready,
    input wire [4-1:0] ext_arid,
    input wire [27:0] ext_araddr,
    input wire [8-1:0] ext_arlen,
    input wire [3-1:0] ext_arsize,
    input wire [2-1:0] ext_arburst,
    input wire  ext_arvalid,
    input wire  ext_rready,
    output wire  ext_awready,
    output wire  ext_wready,
    output wire [4-1:0] ext_bid,
    output wire [2-1:0] ext_bresp,
    output wire  ext_bvalid,
    output wire  ext_arready,
    output wire [4-1:0] ext_rid,
    output wire [128-1:0] ext_rdata,
    output wire [2-1:0] ext_rresp,
    output wire  ext_rlast,
    output wire  ext_rvalid,

    input wire [3:0] debug_word,
    output reg [31:0] debug_data,
    output wire dfi_clk_out, control_ready,
    output wire dfi_reset_n,
    output wire [447:0] status_words,
    output wire [19:0] init_status,
    output wire [0:0] ddr_ck_p,ddr_ck_n,ddr_cke,ddr_odt,ddr_cs_n,
    output wire ddr_reset_n,ddr_ras_n,ddr_cas_n,ddr_we_n,
    output wire [2:0] ddr_ba,
    output wire [13:0] ddr_addr,
    inout wire [1:0] ddr_dqs_p,ddr_dqs_n,ddr_dm,
    inout wire [15:0] ddr_dq
);
    wire clk_ref;
    generate if(ADD_REF_BUFG) begin: ref_buffer
        PH1_LOGIC_BUFG u_ref_buf (.i(ref_clk_100m),.o(clk_ref));
    end else begin: shared_ref
        assign clk_ref=ref_clk_100m;
    end endgenerate
    wire pll_locked,phy_reset_n,cal_done;
    wire [7:0] cal_error,cal_step;
    wire [3:0] bid,rid;
    wire [27:0] awaddr,araddr;
    wire [7:0] awlen,arlen;
    wire [2:0] awsize,arsize;
    wire [1:0] awburst,arburst,bresp,rresp;
    wire awvalid,awready,wlast,wvalid,wready,bvalid,bready;
    wire arvalid,arready,rlast,rvalid,rready;
    wire [127:0] wdata,rdata;
    wire [15:0] wstrb;
    wire busy,done,passed,raw_passed,bist_enabled;
    wire [3:0] raw_fault,awid,arid,fault;
    assign bist_busy=busy;assign bist_done=done;assign bist_passed=passed;
    assign passed=raw_passed&&response_faults==0;
    assign fault=response_faults!=0?4'd8:raw_fault;
    assign bist_fault=fault;
    assign external_reset_n=local_reset_n&&external_enabled;
    always @(posedge dfi_clk_out or negedge local_reset_n)
        if(!local_reset_n)bist_start_rejected<=0;
        else if(bist_start&&(!bist_enabled||!control_ready||response_faults!=0||busy))bist_start_rejected<=1;


    wire [31:0] writes,reads;
    wire [27:0] bad_addr;
    wire [127:0] expected_data,observed_data;

    // Asynchronous assertion, clock-local release after PHY clock/reset available.
    wire reset_release=reset_n && pll_locked && phy_reset_n;
    reg [2:0] reset_pipe;
    always @(posedge dfi_clk_out or negedge reset_release)
        if(!reset_release) reset_pipe<=0;
        else reset_pipe<={reset_pipe[1:0],1'b1};
    wire local_reset_n=reset_pipe[2];
    assign dfi_reset_n=local_reset_n;
    assign init_status={cal_step,cal_error,control_ready,cal_done,phy_reset_n,pll_locked};
    // Completion/error originate in the vendor initialization logic. Synchronize
    // flags. Error details/step are advisory samples, not coherent event records.
    reg [1:0] init_sync,error_sync;
    always @(posedge dfi_clk_out or negedge local_reset_n)
        if(!local_reset_n) begin init_sync<=0;error_sync<=0;end
        else begin init_sync<={init_sync[0],cal_done};error_sync<={error_sync[0],|cal_error};end
    assign control_ready=local_reset_n && init_sync[1] && !error_sync[1];
    assign status_words={
        {12'b0,init_status}, observed_data, expected_data,
        {4'b0,bad_addr}, reads, writes,
        {16'b0,cal_error,1'b0,fault,passed,done,busy},32'h44445231};
    wire [4-1:0] b_awid;
    wire [27:0] b_awaddr;
    wire [8-1:0] b_awlen;
    wire [3-1:0] b_awsize;
    wire [2-1:0] b_awburst;
    wire  b_awvalid;
    wire [128-1:0] b_wdata;
    wire [16-1:0] b_wstrb;
    wire  b_wlast;
    wire  b_wvalid;
    wire  b_bready;
    wire [4-1:0] b_arid;
    wire [27:0] b_araddr;
    wire [8-1:0] b_arlen;
    wire [3-1:0] b_arsize;
    wire [2-1:0] b_arburst;
    wire  b_arvalid;
    wire  b_rready;
    wire  b_awready;
    wire  b_wready;
    wire [4-1:0] b_bid;
    wire [2-1:0] b_bresp;
    wire  b_bvalid;
    wire  b_arready;
    wire [4-1:0] b_rid;
    wire [128-1:0] b_rdata;
    wire [2-1:0] b_rresp;
    wire  b_rlast;
    wire  b_rvalid;
    assign b_awid=4'd0;assign b_arid=4'd0;
    ddr_axi_bist #(.ADDR_WIDTH(28),.WORDS(BIST_WORDS),.TIMEOUT_CYCLES(BIST_TIMEOUT)) u_bist (
        .clk(dfi_clk_out),.rst_n(local_reset_n),.start(bist_start&&bist_enabled&&control_ready&&response_faults==0&&!busy),
        .init_done(init_sync[1]),.init_error({7'b0,error_sync[1]}),
        .busy(busy),.done(done),.passed(raw_passed),.fault(raw_fault),.writes(writes),.reads(reads),
        .first_bad_addr(bad_addr),.expected_data(expected_data),.observed_data(observed_data),
        .awaddr(b_awaddr),.awlen(b_awlen),.awsize(b_awsize),.awburst(b_awburst),.awvalid(b_awvalid),.awready(b_awready),
        .wdata(b_wdata),.wstrb(b_wstrb),.wlast(b_wlast),.wvalid(b_wvalid),.wready(b_wready),
        .bresp(b_bresp),.bvalid(b_bvalid),.bready(b_bready),
        .araddr(b_araddr),.arlen(b_arlen),.arsize(b_arsize),.arburst(b_arburst),.arvalid(b_arvalid),.arready(b_arready),
        .rdata(b_rdata),.rresp(b_rresp),.rlast(b_rlast),.rvalid(b_rvalid),.rready(b_rready)
    );
    afc03_axi_owner_lock #(.ADDR_WIDTH(28)) owner_mux(
.clk(dfi_clk_out),
.reset_n(local_reset_n),
.control_ready(control_ready),
.select_valid(select_valid),
.select_ready(select_ready),
.select_owner(select_owner),
.select_result_valid(select_result_valid),
.select_result_ready(select_result_ready),
.select_result_ok(select_result_ok),
.select_result_error(select_result_error),
.owner(owner),
.external_enabled(external_enabled),
.bist_enabled(bist_enabled),
.response_faults(response_faults),
.last_bid(last_bid),
.last_rid(last_rid),
.last_bresp(last_bresp),
.last_rresp(last_rresp),
.b_awid(b_awid),
.b_awaddr(b_awaddr),
.b_awlen(b_awlen),
.b_awsize(b_awsize),
.b_awburst(b_awburst),
.b_awvalid(b_awvalid),
.b_wdata(b_wdata),
.b_wstrb(b_wstrb),
.b_wlast(b_wlast),
.b_wvalid(b_wvalid),
.b_bready(b_bready),
.b_arid(b_arid),
.b_araddr(b_araddr),
.b_arlen(b_arlen),
.b_arsize(b_arsize),
.b_arburst(b_arburst),
.b_arvalid(b_arvalid),
.b_rready(b_rready),
.b_awready(b_awready),
.b_wready(b_wready),
.b_bid(b_bid),
.b_bresp(b_bresp),
.b_bvalid(b_bvalid),
.b_arready(b_arready),
.b_rid(b_rid),
.b_rdata(b_rdata),
.b_rresp(b_rresp),
.b_rlast(b_rlast),
.b_rvalid(b_rvalid),
.e_awid(ext_awid),
.e_awaddr(ext_awaddr),
.e_awlen(ext_awlen),
.e_awsize(ext_awsize),
.e_awburst(ext_awburst),
.e_awvalid(ext_awvalid),
.e_wdata(ext_wdata),
.e_wstrb(ext_wstrb),
.e_wlast(ext_wlast),
.e_wvalid(ext_wvalid),
.e_bready(ext_bready),
.e_arid(ext_arid),
.e_araddr(ext_araddr),
.e_arlen(ext_arlen),
.e_arsize(ext_arsize),
.e_arburst(ext_arburst),
.e_arvalid(ext_arvalid),
.e_rready(ext_rready),
.e_awready(ext_awready),
.e_wready(ext_wready),
.e_bid(ext_bid),
.e_bresp(ext_bresp),
.e_bvalid(ext_bvalid),
.e_arready(ext_arready),
.e_rid(ext_rid),
.e_rdata(ext_rdata),
.e_rresp(ext_rresp),
.e_rlast(ext_rlast),
.e_rvalid(ext_rvalid),
.m_awid(awid),
.m_awaddr(awaddr),
.m_awlen(awlen),
.m_awsize(awsize),
.m_awburst(awburst),
.m_awvalid(awvalid),
.m_wdata(wdata),
.m_wstrb(wstrb),
.m_wlast(wlast),
.m_wvalid(wvalid),
.m_bready(bready),
.m_arid(arid),
.m_araddr(araddr),
.m_arlen(arlen),
.m_arsize(arsize),
.m_arburst(arburst),
.m_arvalid(arvalid),
.m_rready(rready),
.m_awready(awready),
.m_wready(wready),
.m_bid(bid),
.m_bresp(bresp),
.m_bvalid(bvalid),
.m_arready(arready),
.m_rid(rid),
.m_rdata(rdata),
.m_rresp(rresp),
.m_rlast(rlast),
.m_rvalid(rvalid));
    afc03_ddr u_ddr (
        .sys_clk(clk_ref),.sys_rst_n(reset_n),
        .ddr_ck_p(ddr_ck_p),.ddr_ck_n(ddr_ck_n),.ddr_reset_n(ddr_reset_n),
        .ddr_cke(ddr_cke),.ddr_odt(ddr_odt),.ddr_cs_n(ddr_cs_n),
        .ddr_ras_n(ddr_ras_n),.ddr_cas_n(ddr_cas_n),.ddr_we_n(ddr_we_n),
        .ddr_ba(ddr_ba),.ddr_addr(ddr_addr),.ddr_dqs_p(ddr_dqs_p),.ddr_dqs_n(ddr_dqs_n),
        .ddr_dq(ddr_dq),.ddr_dm(ddr_dm),
        .dfi_clk(dfi_clk_out),.pll_locked(pll_locked),.ddrphy_rst_n(phy_reset_n),
        .ddr_init_cal_done(cal_done),.ddr_init_cal_err(cal_error),.ddr_init_cal_step(cal_step),
        .axi_aclk(dfi_clk_out),.axi_aresetn(local_reset_n),
        .axi_awid(awid),.axi_awaddr(awaddr),.axi_awlen(awlen),.axi_awsize(awsize),
        .axi_awburst(awburst),.axi_awlock(1'b0),.axi_awcache(4'b0),.axi_awprot(3'b0),.axi_awqos(4'b0),
        .axi_awvalid(awvalid),.axi_awready(awready),
        .axi_wdata(wdata),.axi_wstrb(wstrb),.axi_wlast(wlast),.axi_wvalid(wvalid),.axi_wready(wready),
        .axi_bid(bid),.axi_bresp(bresp),.axi_bvalid(bvalid),.axi_bready(bready),
        .axi_arid(arid),.axi_araddr(araddr),.axi_arlen(arlen),.axi_arsize(arsize),
        .axi_arburst(arburst),.axi_arlock(1'b0),.axi_arcache(4'b0),.axi_arprot(3'b0),.axi_arqos(4'b0),
        .axi_arvalid(arvalid),.axi_arready(arready),
        .axi_rid(rid),.axi_rdata(rdata),.axi_rresp(rresp),.axi_rlast(rlast),.axi_rvalid(rvalid),.axi_rready(rready),
        .pzq_cal_done_i(1'b0),.user_update(1'b0),.user_ram_addr(8'b0),
        .user_ram_wr_en(1'b0),.user_ram_rd_en(1'b0),.user_ram_wr_data(32'b0),.uart_rxd(1'b1)
    );
    always @* begin
        case(debug_word)
            0: debug_data=32'h44445231;
            1: debug_data={16'b0,cal_error,1'b0,fault,passed,done,busy};
            2: debug_data=writes;
            3: debug_data=reads;
            4: debug_data={4'b0,bad_addr};
            5: debug_data=expected_data[31:0];
            6: debug_data=expected_data[63:32];
            7: debug_data=expected_data[95:64];
            8: debug_data=expected_data[127:96];
            9: debug_data=observed_data[31:0];
            10: debug_data=observed_data[63:32];
            11: debug_data=observed_data[95:64];
            12: debug_data=observed_data[127:96];
            13: debug_data={20'b0,cal_step,control_ready,cal_done,phy_reset_n,pll_locked};
            default: debug_data=0;
        endcase
    end
endmodule
