// The camera supplies Content-Length for each JPEG. Decode one part at a time,
// accepting arbitrary TCP chunk boundaries and bounding incomplete-frame memory.
export class MjpegParser {
 private buffer=new Uint8Array(0)
 private expected=0
 push(chunk:Uint8Array):Uint8Array[] {
  const next=new Uint8Array(this.buffer.length+chunk.length)
  next.set(this.buffer);next.set(chunk,this.buffer.length);this.buffer=next
  const frames:Uint8Array[]=[]
  while(this.buffer.length){
   if(!this.expected){
    let end=-1
    for(let i=0;i+3<this.buffer.length;i++)if(this.buffer[i]===13&&this.buffer[i+1]===10&&this.buffer[i+2]===13&&this.buffer[i+3]===10){end=i;break}
    if(end<0){if(this.buffer.length>8192)throw Error('Invalid preview header');break}
    const header=new TextDecoder().decode(this.buffer.subarray(0,end))
    const match=/content-length:\s*(\d+)/i.exec(header)
    if(!match)throw Error('Preview frame has no length')
    this.expected=Number(match[1])
    if(this.expected<2||this.expected>5*1024*1024)throw Error('Invalid preview frame size')
    this.buffer=this.buffer.slice(end+4)
   }
   if(this.buffer.length<this.expected)break
   const frame=this.buffer.slice(0,this.expected)
   if(frame[0]!==255||frame[1]!==216)throw Error('Invalid JPEG preview')
   frames.push(frame);this.buffer=this.buffer.slice(this.expected);this.expected=0
  }
  return frames
 }
}
