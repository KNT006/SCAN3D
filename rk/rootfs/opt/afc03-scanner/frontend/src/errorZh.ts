/** Display concise Chinese diagnostics; retain raw exceptions in the console/logs. */
export function errorZh(value: unknown): string {
 const raw=value instanceof Error?value.message:typeof value==='string'?value:JSON.stringify(value??'')
 if(!raw)return '操作失败，请稍后重试。'
 const rules:[RegExp,string][]=[
  [/Initial colo[u]?r exposure/i,'起始彩色图亮度检查未通过，请检查补光灯、挡板和曝光；深色物体也可能触发检查。'],
  [/Initial dual-laser/i,'起始双激光有效点数不足，请检查激光和物体位置。'],
  [/Full-turn image closure/i,'整圈采集已结束，但首尾一致性检查未通过，请复核结果。'],
  [/Operator stop/i,'扫描已按停止请求结束，已采集数据已保留。'],
  [/Remaining capacity below projected scan size plus reserve/i,'剩余存储空间不足以完成整圈扫描，已停止并保留采集数据。请先归档清理，或改用较大角度步长开始新扫描。'],
  [/Data partition below 1 GiB reserve|Insufficient startup storage/i,'存储空间低于扫描所需的保留容量，已停止。请先归档清理已有数据。'],
  [/session|pulse.*(mismatch|unknown)|may have|uncertain|do not retry/i,'电机会话或脉冲状态异常，转动结果不确定。请检查设备和当前位置，不要重复发送转动指令。'],
  [/no space left|disk.*full/i,'存储空间不足，请清理或归档已有数据。'],
  [/out of memory|bad_alloc|cannot allocate|MemoryError|killed.*9/i,'可用内存不足，请降低处理规模或等待其他任务结束。'],
  [/timed?\s*out|timeout|TimeoutError/i,'设备响应超时。若刚才发送了转动指令，请先确认设备状态，不要重复点击。'],
  [/Failed to fetch|NetworkError|network.*(error|lost)|Load failed|connection.*(refused|reset)|ECONN/i,'设备连接中断，请检查网络和板端服务。'],
  [/abort/i,'请求已取消或超时，请检查当前任务状态。'],
  [/permission denied|not permitted|forbidden/i,'操作权限不足，请检查服务与文件权限。'],
  [/no such file|not found|ENOENT/i,'所需文件或资源不存在，请刷新列表或重新生成。'],
  [/busy|resource temporarily unavailable|locked/i,'设备或任务正在使用中，请等待完成后重试。'],
  [/not connected|disconnected|serial.*(missing|unavailable)|broker.*unavailable/i,'控制器未连接，请检查供电和控制线。'],
  [/WebGL|context lost/i,'三维显示不可用，请启用浏览器硬件加速或刷新页面。'],
  [/JSON|unexpected token|unexpected end|invalid.*response/i,'服务返回的数据不完整或格式异常，请刷新后重试。'],
  [/validation|field required|invalid input|unprocessable|bad request/i,'请求参数无效，请检查输入范围和必填项。'],
  [/internal server error|service unavailable|bad gateway/i,'板端服务暂不可用，请稍后重试。'],
  [/^ERR\b/i,'控制器拒绝了命令，请检查连接与设备状态。'],
 ]
 for(const [pattern,message] of rules)if(pattern.test(raw))return message
 if(/[\u3400-\u9fff]/.test(raw)) {
  // Keep Chinese application diagnostics, not appended Python/driver traces.
  const clean=raw.split(/Traceback|\[Errno|\n\s*File /)[0].trim()
  return clean||'操作失败，请查看设备运行日志。'
 }
 return '操作失败，请在运行日志中查看详细原因。'
}
