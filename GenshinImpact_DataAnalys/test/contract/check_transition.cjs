/* Check the encoded logo segment and handoff to the real, interactive deck. */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url'),{chromium}=require('playwright');
async function seek(page,time){
 await page.locator('video').evaluate((video,time)=>new Promise((resolve,reject)=>{video.pause();video.addEventListener('seeked',resolve,{once:true});video.addEventListener('error',reject,{once:true});video.currentTime=time;}),time);
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
}
async function main(){
 const output=path.resolve(process.argv[2]),qa=path.resolve(process.argv[3]||'.pytest_cache/opener_transition_player_qa');await fs.mkdir(qa,{recursive:true});
 const manifest=JSON.parse(await fs.readFile(path.join(output,'build_manifest.json'),'utf8')),transition=manifest.timing.logoTransition;
 assert(transition);
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-extensions','--no-first-run','--allow-file-access-from-files']});
 const results=[];
 try{for(const viewport of [{width:1920,height:1080},{width:390,height:844},{width:1600,height:700}]){
  const page=await browser.newPage({viewport,deviceScaleFactor:1}),errors=[],remote=[];page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/.test(request.url()))remote.push(request.url());});
  await page.goto(pathToFileURL(path.join(output,'index.html')).href);await page.waitForFunction(()=>document.getElementById('video').readyState>=1);
  const frame=page.frameLocator('#deck');await frame.locator('#slide-1').waitFor({state:'attached'});
  await page.locator('#start').click();await page.waitForFunction(()=>document.body.classList.contains('playing'));
  const duration=await page.locator('video').evaluate(video=>video.duration);assert(Math.abs(duration-manifest.duration_seconds)<.1);
  const profile=manifest.timing.flashProfile,flashStart=manifest.timing.flashExpandStart,flashEnd=manifest.timing.flashExpandEnd;
  assert(flashStart<flashEnd&&flashEnd<transition.start);
  await seek(page,flashStart-.1);assert.equal(await page.locator('#handoff').evaluate(node=>getComputedStyle(node).opacity),'0');
  // Start once, then observe actual consecutive playback frames rather than seeking to probes.
  await page.evaluate(()=>{
    window.flashProbes=[];const video=document.getElementById('video'),end=window.openerTiming.flashProfile.resetEnd+.1;
    const observe=(_,metadata)=>{const matrix=new DOMMatrixReadOnly(getComputedStyle(video).transform);window.flashProbes.push({time:metadata.mediaTime,zoom:matrix.a,background:getComputedStyle(document.getElementById('screen')).backgroundColor,overlay:Number(getComputedStyle(document.getElementById('handoff')).opacity),fullscreen:Boolean(document.fullscreenElement)});if(metadata.mediaTime<end)video.requestVideoFrameCallback(observe);};
    video.requestVideoFrameCallback(observe);return video.play();
  });
  await page.waitForFunction(()=>window.flashProbes.at(-1)?.time>=window.openerTiming.flashProfile.resetEnd+.1);
  await page.locator('video').evaluate(video=>video.pause());const flash=await page.evaluate(()=>window.flashProbes);
  assert(flash.length>20);for(let i=0;i<flash.length;i++){
    assert.equal(flash[i].overlay,0);assert.equal(flash[i].fullscreen,false);
    if(i){assert(flash[i].time>flash[i-1].time);if(flash[i].time<profile.solidAt)assert(flash[i].zoom>=flash[i-1].zoom-.00001);}
    if(flash[i].time>=profile.resetEnd)assert(Math.abs(flash[i].zoom-1)<.00001);
  }
  if(viewport.width/viewport.height!==16/9)assert(new Set(flash.filter(row=>row.time<profile.solidAt).map(row=>row.zoom)).size>8);
  await seek(page,41.05);await page.waitForFunction(()=>document.body.classList.contains('white-tail'));assert.equal(await page.locator('#handoff').evaluate(node=>getComputedStyle(node).opacity),'0');
  await seek(page,transition.start+1.6);await page.waitForFunction(()=>document.body.classList.contains('logo-transition'));assert.equal(await page.locator('#handoff').evaluate(node=>getComputedStyle(node).opacity),'0');assert(!(await page.locator('#skip').isVisible()));
  const promptHidden=await page.locator('video').evaluate(video=>{const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=1080;const context=canvas.getContext('2d');context.drawImage(video,0,0,1920,1080);const data=context.getImageData(0,800,1920,280).data;for(let i=0;i<data.length;i+=4)if(data[i]<250||data[i+1]<250||data[i+2]<250)return false;return true;});assert(promptHidden);
  await page.screenshot({path:path.join(qa,`logo_${viewport.width}.png`)});
  await seek(page,transition.start+transition.sourceDuration+.8);await page.screenshot({path:path.join(qa,`motion_${viewport.width}.png`)});
  await seek(page,duration-.2);await page.screenshot({path:path.join(qa,`before_handoff_${viewport.width}.png`)});
  await page.locator('video').evaluate(video=>video.play());await page.waitForFunction(()=>document.body.classList.contains('reveal-deck'));
  assert(await page.evaluate(()=>document.body.classList.contains('seamless-handoff')));assert.equal(await page.locator('#handoff').evaluate(node=>getComputedStyle(node).opacity),'0');
  await frame.locator('#slide-1.active').waitFor();await page.screenshot({path:path.join(qa,`after_handoff_${viewport.width}.png`)});
  assert.equal(await frame.locator('.slide').count(),manifest.logo_transition.cover_slide_count);
  const target=await frame.locator('#slide-1 h1 .genshin-logo').evaluate(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};});
  if(viewport.width===1920)for(const key of ['x','y','width','height'])assert(Math.abs(target[key]-manifest.logo_transition.cover_logo_box[key])<.1);
  await page.keyboard.press('ArrowRight');assert.equal(await frame.locator('.slide.active').getAttribute('id'),'slide-2');
  await page.reload();await page.locator('#skip').click();await page.waitForFunction(()=>document.body.classList.contains('reveal-deck'));await page.waitForFunction(()=>getComputedStyle(document.getElementById('handoff')).opacity==='0');
  await page.keyboard.press('ArrowRight');assert.equal(await page.frameLocator('#deck').locator('.slide.active').getAttribute('id'),'slide-2');assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
  results.push({viewport,duration,flashExpansion:{start:flashStart,end:flashEnd,probes:flash},promptHidden,seamlessHandoff:true,keyboardNavigation:true,skip:true,target,errors,remote});await page.close();
 }}finally{await browser.close();}
 await fs.writeFile(path.join(qa,'verification.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
