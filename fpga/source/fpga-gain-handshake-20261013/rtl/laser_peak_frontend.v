`timescale 1ns/1ps
// Standalone, conservative integer front end. Input is the ROTATED image row,
// after reflect101 Gaussian numerator [1,4,6,4,1], not a raw camera raster line.
// Default equal-height distance tie policy is right-first, user selected.
// Optional legacy-safe mode requests fallback with NO peaks on conflicting ties.
// No source integration, resource/timing/throughput qualification is implied.
module laser_peak_frontend #(
    parameter MAX_WIDTH=2048, parameter MAX_LOCAL=1024,
    // 0: request original RK processing on ties. 1: deterministic right first.
    parameter TIE_POLICY=1,
    // 1: three exact 4-bit radix histogram passes; 0: previous bitwise scans.
    parameter MEDIAN_RADIX=1
)(
    input wire clk, rst_n,
    input wire [47:0] spatial_ranges,input wire spatial_enable,
    input wire sample_we, input wire [11:0] sample_addr, sample16,
    input wire start, input wire [11:0] width, roi_left, roi_right,
    output reg busy, done, error, fallback, tie_conflict,
    output reg [13:0] base32,
    output reg peak_valid, output reg [11:0] peak_x,
    input wire peak_ready,
    output reg [11:0] peak_count
);
    (* ram_style="bram" *) reg [11:0] samples [0:MAX_WIDTH-1];
    // A single 26-bit candidate table replaces four asynchronous arrays.
    // [25]chosen [24]active [23:12]height [11:0]location.
    (* ram_style="bram" *) reg [25:0] candidates [0:MAX_LOCAL-1];
    reg [11:0] candidate_read_addr,candidate_write_addr;
    reg [25:0] candidate_q,candidate_write_data;
    reg candidate_write_enable;
    reg [11:0] recent_x[0:2],recent_height[0:2];
    always @(posedge clk)begin
        if(candidate_write_enable)candidates[candidate_write_addr]<=candidate_write_data;
        candidate_q<=candidates[candidate_read_addr];
    end
    reg [11:0] read_addr, sample_q;
    always @(posedge clk) begin
        if(sample_we && !busy && sample_addr<MAX_WIDTH) samples[sample_addr]<=sample16;
        sample_q<=samples[read_addr];
    end
    localparam IDLE=0, WAIT_RD=1, MED_SCAN=2, MED_DECIDE=3, LOCAL_FIRST=4,
       LOCAL_SCAN=5, LOCAL_END=6, FIND_INIT=7, FIND_SCAN=8, SELECT=9,
       SUPPRESS=10, OUTPUT_NEXT=11, LEFT_SCAN=12, RIGHT_START=13,
       RIGHT_SCAN=14, PROMINENCE=15, SEND=16,
       RADIX_CLEAR=17,RADIX_SCAN=18,RADIX_PICK=19,WAIT_CANDIDATE=20,FIND_END=21,OUTPUT_PICK=22;
    reg [4:0] state, resume;
    reg [11:0] left, right, pos, median_lo, median_hi, count_lo, count_hi;
    reg [11:0] rank_lo, rank_hi;
    reg [3:0] bit_index;
    wire [11:0] bit_value=12'd1<<bit_index;
    wire [11:0] threshold_lo=median_lo|bit_value;
    wire [11:0] threshold_hi=median_hi|bit_value;
    wire [11:0] next_lo=count_lo<=rank_lo ? threshold_lo:median_lo;
    wire [11:0] next_hi=count_hi<=rank_hi ? threshold_hi:median_hi;
    // Two 16-bin counters preserve independently branching lower/upper ranks.
    // Register arrays are intentional here (384 data bits), not a BRAM claim.
    reg [11:0] histogram_lo[0:15],histogram_hi[0:15];
    reg [1:0] digit;
    reg [3:0] bucket;
    reg selected_lo,selected_hi;
    wire [11:0] prefix_mask=(digit==0)?12'h000:((digit==1)?12'hf00:12'hff0);
    wire [3:0] sample_digit=(digit==0)?sample_q[11:8]:((digit==1)?sample_q[7:4]:sample_q[3:0]);
    wire [11:0] bucket_digit=(digit==0)?{bucket,8'b0}:((digit==1)?{4'b0,bucket,4'b0}:{8'b0,bucket});
    wire pick_lo=!selected_lo && rank_lo<histogram_lo[bucket];
    wire pick_hi=!selected_hi && rank_hi<histogram_hi[bucket];
    wire [11:0] radix_next_lo=pick_lo?(median_lo|bucket_digit):median_lo;
    wire [11:0] radix_next_hi=pick_hi?(median_hi|bucket_digit):median_hi;
    reg [11:0] previous, plateau_start, local_count, scan, best, best_height,best_x;
    reg rising, found;
    wire [12:0] midpoint_sum={1'b0,plateau_start}+{1'b0,pos}-13'd1;
    wire [11:0] midpoint=midpoint_sum[12:1];
    wire spatial_reject=spatial_enable &&
        ((midpoint>=spatial_ranges[11:0] && midpoint<=spatial_ranges[23:12]) ||
         (midpoint>=spatial_ranges[35:24] && midpoint<=spatial_ranges[47:36]));
    reg [11:0] output_index, current_x, current_height, left_min, right_min;
    wire [11:0] higher_min=left_min>right_min ? left_min:right_min;
    // One combinational write-port mux, followed by one synchronous RAM
    // process. No memory writes or reset branches live in the state machine.
    always @* begin
        candidate_write_enable=0;candidate_write_addr=0;candidate_write_data=0;
        if(rst_n)case(state)
            LOCAL_SCAN:if(sample_q<previous && rising && !spatial_reject && local_count<MAX_LOCAL)begin
                candidate_write_enable=1;candidate_write_addr=local_count;
                candidate_write_data={1'b0,1'b1,previous,midpoint};
            end
            SELECT:begin
                candidate_write_enable=1;candidate_write_addr=best;
                candidate_write_data={1'b1,1'b0,best_height,best_x};
            end
            SUPPRESS:if((candidate_q[11:0]>=best_x && candidate_q[11:0]-best_x<8)||
                        (candidate_q[11:0]<best_x && best_x-candidate_q[11:0]<8))begin
                candidate_write_enable=1;candidate_write_addr=scan;
                candidate_write_data={candidate_q[25],1'b0,candidate_q[23:0]};
            end
        endcase
    end
    integer j;
    task read_candidate;
        input [11:0] address;input[4:0] target;
        begin candidate_read_addr<=address;resume<=target;state<=WAIT_CANDIDATE;end
    endtask
    task read_at;
        input [11:0] address; input [4:0] target;
        begin read_addr<=address;resume<=target;state<=WAIT_RD;end
    endtask
    task finish;
        begin busy<=0;done<=1;state<=IDLE;end
    endtask
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;resume<=IDLE;busy<=0;done<=0;error<=0;
            fallback<=0;tie_conflict<=0;base32<=0;peak_valid<=0;peak_x<=0;peak_count<=0;
            left<=0;right<=0;pos<=0;median_lo<=0;median_hi<=0;count_lo<=0;count_hi<=0;
            rank_lo<=0;rank_hi<=0;bit_index<=0;previous<=0;plateau_start<=0;
            digit<=0;bucket<=0;selected_lo<=0;selected_hi<=0;
            local_count<=0;scan<=0;best<=0;best_height<=0;best_x<=0;rising<=0;found<=0;
            for(j=0;j<3;j=j+1)begin recent_x[j]<=0;recent_height[j]<=0;end
            output_index<=0;current_x<=0;current_height<=0;left_min<=0;right_min<=0;
        end else begin
            done<=0;
            case(state)
            IDLE:if(start) begin
                error<=0;fallback<=0;tie_conflict<=0;peak_valid<=0;peak_count<=0;base32<=0;
                if(width<3 || width>MAX_WIDTH || roi_left>=roi_right || roi_right>=width) begin
                    error<=1;done<=1;
                end else begin
                    busy<=1;left<=roi_left;right<=roi_right;pos<=roi_left;
                    median_lo<=0;median_hi<=0;count_lo<=0;count_hi<=0;bit_index<=11;
                    rank_lo<=(roi_right-roi_left)>>1;
                    rank_hi<=(roi_right-roi_left+12'd1)>>1;
                    local_count<=0;rising<=0;
                    if(MEDIAN_RADIX)begin digit<=0;bucket<=0;selected_lo<=0;selected_hi<=0;state<=RADIX_CLEAR;end
                    else read_at(roi_left,MED_SCAN);
                end
            end
            WAIT_RD:state<=resume;
            WAIT_CANDIDATE:state<=resume;
            MED_SCAN:begin
                if(sample_q>4080)begin error<=1;finish;end
                else begin
                    if(sample_q<threshold_lo)count_lo<=count_lo+1;
                    if(sample_q<threshold_hi)count_hi<=count_hi+1;
                    if(pos==right)state<=MED_DECIDE;
                    else begin pos<=pos+1;read_at(pos+1,MED_SCAN);end
                end
            end
            MED_DECIDE:begin
                median_lo<=next_lo;median_hi<=next_hi;
                if(bit_index==0)begin
                    base32<={2'b0,next_lo}+{2'b0,next_hi};
                    pos<=left;read_at(left,LOCAL_FIRST);
                end else begin
                    bit_index<=bit_index-1;count_lo<=0;count_hi<=0;pos<=left;
                    read_at(left,MED_SCAN);
                end
            end
            RADIX_CLEAR:begin
                histogram_lo[bucket]<=0;histogram_hi[bucket]<=0;
                if(bucket==15)begin pos<=left;read_at(left,RADIX_SCAN);end
                else bucket<=bucket+1;
            end
            RADIX_SCAN:begin
                if(sample_q>4080)begin error<=1;finish;end
                else begin
                    if((sample_q&prefix_mask)==median_lo)
                        histogram_lo[sample_digit]<=histogram_lo[sample_digit]+1;
                    if((sample_q&prefix_mask)==median_hi)
                        histogram_hi[sample_digit]<=histogram_hi[sample_digit]+1;
                    if(pos==right)begin bucket<=0;selected_lo<=0;selected_hi<=0;state<=RADIX_PICK;end
                    else begin pos<=pos+1;read_at(pos+1,RADIX_SCAN);end
                end
            end
            RADIX_PICK:begin
                if(!selected_lo)begin
                    if(pick_lo)begin median_lo<=radix_next_lo;selected_lo<=1;end
                    else rank_lo<=rank_lo-histogram_lo[bucket];
                end
                if(!selected_hi)begin
                    if(pick_hi)begin median_hi<=radix_next_hi;selected_hi<=1;end
                    else rank_hi<=rank_hi-histogram_hi[bucket];
                end
                if((selected_lo||pick_lo)&&(selected_hi||pick_hi))begin
                    if(digit==2)begin
                        base32<={2'b0,radix_next_lo}+{2'b0,radix_next_hi};
                        pos<=left;read_at(left,LOCAL_FIRST);
                    end else begin
                        digit<=digit+1;bucket<=0;selected_lo<=0;selected_hi<=0;state<=RADIX_CLEAR;
                    end
                end else if(bucket==15)begin error<=1;finish;end
                else bucket<=bucket+1;
            end
            LOCAL_FIRST:begin previous<=sample_q;pos<=left+1;read_at(left+1,LOCAL_SCAN);end
            LOCAL_SCAN:begin
                previous<=sample_q;
                if(sample_q>previous)begin plateau_start<=pos;rising<=1;end
                else if(sample_q<previous)begin
                    rising<=0;
                    if(rising && !spatial_reject)begin
                        if(local_count==MAX_LOCAL)begin error<=1;finish;end
                        else begin
                            local_count<=local_count+1;
                            // Only the three preceding local maxima can be within
                            // distance<8. Explicit history avoids multi-port RAM.
                            for(j=0;j<3;j=j+1)
                                if(local_count>j && midpoint-recent_x[j]<8 &&
                                   previous==recent_height[j])tie_conflict<=1;
                            recent_x[2]<=recent_x[1];recent_x[1]<=recent_x[0];recent_x[0]<=midpoint;
                            recent_height[2]<=recent_height[1];recent_height[1]<=recent_height[0];recent_height[0]<=previous;
                        end
                    end
                end
                if(!(sample_q<previous && rising && !spatial_reject && local_count==MAX_LOCAL))begin
                    if(pos==right)state<=LOCAL_END;
                    else begin pos<=pos+1;read_at(pos+1,LOCAL_SCAN);end
                end
            end
            LOCAL_END:begin
                if(tie_conflict && TIE_POLICY==0)begin fallback<=1;finish;end
                else state<=FIND_INIT;
            end
            FIND_INIT:begin
                scan<=0;found<=0;best<=0;best_height<=0;best_x<=0;
                if(local_count==0)begin output_index<=0;state<=OUTPUT_NEXT;end
                else read_candidate(0,FIND_SCAN);
            end
            FIND_SCAN:begin
                if(candidate_q[24] && (!found || candidate_q[23:12]>=best_height))begin
                    found<=1;best<=scan;best_height<=candidate_q[23:12];best_x<=candidate_q[11:0];
                end
                if(scan==local_count-1'b1)state<=FIND_END;
                else begin scan<=scan+1'b1;read_candidate(scan+1'b1,FIND_SCAN);end
            end
            FIND_END:begin
                if(found)state<=SELECT;
                else begin output_index<=0;state<=OUTPUT_NEXT;end
            end
            SELECT:begin scan<=0;read_candidate(0,SUPPRESS);end
            SUPPRESS:begin
                if(scan==local_count-1'b1)state<=FIND_INIT;
                else begin scan<=scan+1'b1;read_candidate(scan+1'b1,SUPPRESS);end
            end
            OUTPUT_NEXT:begin
                if(output_index==local_count)finish;
                else read_candidate(output_index,OUTPUT_PICK);
            end
            OUTPUT_PICK:begin
                if(!candidate_q[25])begin output_index<=output_index+1'b1;state<=OUTPUT_NEXT;end
                else begin
                    current_x<=candidate_q[11:0];current_height<=candidate_q[23:12];
                    left_min<=candidate_q[23:12];right_min<=candidate_q[23:12];
                    pos<=candidate_q[11:0]-1'b1;read_at(candidate_q[11:0]-1'b1,LEFT_SCAN);
                end
            end
            LEFT_SCAN:begin
                if(sample_q>current_height)state<=RIGHT_START;
                else begin
                    if(sample_q<left_min)left_min<=sample_q;
                    if(pos==left)state<=RIGHT_START;
                    else begin pos<=pos-1;read_at(pos-1,LEFT_SCAN);end
                end
            end
            RIGHT_START:begin pos<=current_x+1;read_at(current_x+1,RIGHT_SCAN);end
            RIGHT_SCAN:begin
                if(sample_q>current_height)state<=PROMINENCE;
                else begin
                    if(sample_q<right_min)right_min<=sample_q;
                    if(pos==right)state<=PROMINENCE;
                    else begin pos<=pos+1;read_at(pos+1,RIGHT_SCAN);end
                end
            end
            PROMINENCE:begin
                if(current_height-higher_min>=288)begin peak_x<=current_x;peak_valid<=1;state<=SEND;end
                else begin output_index<=output_index+1;state<=OUTPUT_NEXT;end
            end
            SEND:if(peak_ready)begin
                peak_valid<=0;peak_count<=peak_count+1;output_index<=output_index+1;state<=OUTPUT_NEXT;
            end
            default:begin error<=1;peak_valid<=0;finish;end
            endcase
        end
    end
endmodule
