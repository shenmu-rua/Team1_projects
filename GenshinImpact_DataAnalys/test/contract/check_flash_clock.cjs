/* Execute the player with a small DOM stub. This does not launch or verify a browser. */
const fs=require('node:fs/promises'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
async function main(){
 const output=path.resolve(process.argv[2]),html=await fs.readFile(path.join(output,'index.html'),'utf8');
 const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
 const manifest=JSON.parse(await fs.readFile(path.join(output,'build_manifest.json'),'utf8')),profile=manifest.timing.flashProfile;
 assert(profile&&profile.curve.length>10);assert(profile.curve.at(-1)[0]<profile.solidAt&&profile.resetEnd<manifest.timing.logoTransition.start);
 const results=[];
 for(const viewport of [{width:1920,height:1080},{width:1280,height:800},{width:390,height:844},{width:1600,height:700}]){
  for(const frameCallback of [true,false]){
   let nextFrame,nextAnimation,fullscreen=0;const handlers={},classes=new Set(),events={};
   const body={classList:{add:(...names)=>names.forEach(name=>classes.add(name)),remove:(...names)=>names.forEach(name=>classes.delete(name)),toggle:(name,on)=>on?classes.add(name):classes.delete(name),contains:name=>classes.has(name)}};
   const elements={screen:{style:{},getBoundingClientRect:()=>({...viewport})},deck:{addEventListener:(type,fn)=>{handlers[`deck:${type}`]=fn;}},start:{},skip:{},error:{},video:{style:{},videoWidth:1920,videoHeight:1080,currentTime:0,paused:true,play:async function(){this.paused=false;},pause:function(){this.paused=true;},addEventListener:(type,fn)=>{events[type]=fn;}}};
   if(frameCallback)elements.video.requestVideoFrameCallback=fn=>{nextFrame=fn;};
   const window={addEventListener:(type,fn)=>{handlers[type]=fn;}};
   vm.runInNewContext(script,{document:{body,getElementById:id=>elements[id],addEventListener:()=>{},documentElement:{requestFullscreen:async()=>{fullscreen++;}}},window,requestAnimationFrame:fn=>{nextAnimation=fn;},console});
   await elements.start.onclick();assert.equal(fullscreen,0);assert.equal(events.timeupdate,undefined);
   const samples=[],start=profile.curve[0][0]-.2,end=profile.resetEnd+.2;
   for(let time=start;time<=end;time+=1/60){
    // The playback clock deliberately leads the presented frame. rVFC must win.
    elements.video.currentTime=time+(frameCallback?.013:0);
    if(frameCallback)nextFrame(0,{mediaTime:time});else nextAnimation();
    const zoom=Number(elements.video.style.transform.match(/scale\(([^)]+)\)/)[1]);
    assert(Number.isFinite(zoom)&&zoom>=1);
    const background=elements.screen.style.backgroundColor;
    if(time<profile.solidAt)assert.equal(background,'#030611');else assert(background.startsWith('rgb('));
    if(time>=profile.resetEnd)assert.equal(zoom,1);
    if(samples.length&&time<profile.solidAt)assert(zoom>=samples.at(-1).zoom-1e-10);
    if(samples.length&&zoom<samples.at(-1).zoom-1e-10)assert(time>=profile.solidAt);
    samples.push({time,zoom,background});
   }
   const max=Math.max(...samples.map(row=>row.zoom)),ratio=viewport.width/viewport.height;
   assert(Math.abs(max-Math.max(ratio/(16/9),(16/9)/ratio))<1e-6);
   if(ratio!==16/9)assert(new Set(samples.filter(row=>row.time<profile.solidAt).map(row=>row.zoom)).size>15);
   const beforeResize=elements.video.style.transform;handlers.resize();assert.equal(elements.video.style.transform,beforeResize);
   results.push({viewport,clock:frameCallback?'presented media frames':'animation frame fallback',samples:samples.length,maxZoom:max,automaticFullscreenRequests:fullscreen,resetOnlyDuringNativeWhite:true});
  }
 }
 const result={method:'DOM-stub continuous frame simulation; no browser',browserPlaybackVerified:false,results};
 if(process.argv[3])await fs.writeFile(path.resolve(process.argv[3]),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
