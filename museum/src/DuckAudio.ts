export class DuckAudio {context:AudioContext|null=null;enabled=false;
 async chirp(){if(!this.enabled)return;try{this.context??=new AudioContext();await this.context.resume();const c=this.context,o=c.createOscillator(),g=c.createGain();o.type='triangle';o.frequency.setValueAtTime(430,c.currentTime);o.frequency.exponentialRampToValueAtTime(220,c.currentTime+.15);g.gain.setValueAtTime(.035,c.currentTime);g.gain.exponentialRampToValueAtTime(.001,c.currentTime+.2);o.connect(g);g.connect(c.destination);o.start();o.stop(c.currentTime+.21);o.onended=()=>{o.disconnect();g.disconnect();};}catch{}}
 dispose(){void this.context?.close();}
}
