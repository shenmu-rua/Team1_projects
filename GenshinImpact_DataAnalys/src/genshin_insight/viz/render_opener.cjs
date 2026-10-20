/* Transparent ADS foreground over the unmodified motion of the supplied video. */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {once}=require('node:events');
const {pathToFileURL}=require('node:url'),{spawn}=require('node:child_process'),{chromium}=require('playwright');

async function command(executable,args){
  return new Promise((resolve,reject)=>{const process=spawn(executable,args,{windowsHide:true,stdio:['ignore','ignore','pipe']});let error='';process.stderr.on('data',data=>{error=(error+data.toString()).slice(-6000);});process.on('error',reject);process.on('exit',code=>code===0?resolve(error):reject(new Error(error)));});
}
async function exportFilm(page,output,work,ffmpeg,timing,qa){
  const temporary=path.join(output,'opening.partial.mp4');
  const args=['-y','-hide_banner','-i',path.join(work,'assets/background.mp4'),'-f','image2pipe','-framerate','30','-c:v','png','-i','pipe:0','-filter_complex','[0:v]setsar=1[base];[base][1:v]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[out]','-map','[out]','-map','0:a:0','-c:v','libx264','-preset','slow','-crf','23','-r',String(timing.fps),'-c:a','aac','-b:a','160k','-t',String(timing.duration),'-map_metadata','-1','-movflags','+faststart',temporary];
  const encoder=spawn(ffmpeg,args,{windowsHide:true,stdio:['pipe','ignore','pipe']});
  let log='',failure=null;
  encoder.stderr.on('data',data=>{log=(log+data.toString()).slice(-200000);});
  encoder.stdin.on('error',error=>{failure=error;});
  const completion=new Promise(resolve=>{encoder.on('error',error=>{failure=error;resolve(-1);});encoder.on('close',resolve);});
  const count=Math.round(timing.duration*30);
  try{
    for(let frame=0;frame<count;frame++){
      if(failure)throw failure;
      const encoded=await page.evaluate(t=>{const result=window.renderFrame(t);if(result.errors.length)throw new Error(JSON.stringify(result.errors));return document.getElementById('film').toDataURL('image/png').split(',')[1];},frame/30);
      if(!encoder.stdin.write(Buffer.from(encoded,'base64')))await Promise.race([once(encoder.stdin,'drain'),completion.then(()=>{throw new Error(log||'FFmpeg exited before the final frame');})]);
      if(frame%120===0)console.log(`Rendered foreground ${frame}/${count}; background stays ${timing.fps}fps`);
    }
    encoder.stdin.end();
    const code=await completion;
    await fs.writeFile(path.join(qa,'mux.log'),log);
    if(failure||code!==0)throw failure||new Error(log);
    const verification=await command(ffmpeg,['-v','error','-i',temporary,'-f','null','-']);assert.equal(verification.trim(),'');
    await fs.rename(temporary,path.join(output,'开场视频.mp4'));
    console.log(`Verified MP4: ${path.join(output,'开场视频.mp4')}`);
  }catch(error){encoder.stdin.destroy();encoder.kill();await completion;throw error;}
}
async function main(){
  const output=path.resolve(process.argv[2]),ffmpeg=process.argv[3],qaOnly=process.argv.includes('--qa-only');
  const workIndex=process.argv.indexOf('--work'),work=workIndex>=0?path.resolve(process.argv[workIndex+1]):output;
  const qa=path.resolve(__dirname,'../../../.pytest_cache/opener_video_qa');await fs.mkdir(qa,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-extensions','--no-first-run']});
  try{
    const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1}),errors=[],remote=[];
    page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/.test(request.url()))remote.push(request.url());});
    const {timing}=JSON.parse(await fs.readFile(path.join(output,'build_manifest.json'),'utf8')),probes=[];
    if(!qaOnly||await fs.access(path.join(work,'motion.html')).then(()=>true,()=>false)){
    await page.goto(pathToFileURL(path.join(work,'motion.html')).href);await page.waitForFunction(()=>window.filmReady===true);
    for(const time of [2.6,6.8,12.9,20.1,26.4,32.4,38]){
      const result=await page.evaluate(t=>window.seekFilm(t),time);probes.push(result);assert.deepEqual(result.errors,[],`Text outside safe area at ${time}`);
      await page.locator('.stage').screenshot({path:path.join(qa,`scene_${result.scene+1}.png`)});
    }
    for(const time of [0,3.98,4,9.98,10,15.98,16,22.98,23,28.98,29,34.98,35,39.966])assert.deepEqual((await page.evaluate(t=>window.renderFrame(t),time)).errors,[]);
    for(const time of [39.6,39.9,40,40.3,40.6,41,41.18]){
      const result=await page.evaluate(t=>window.seekFilm(t),time);
      assert.deepEqual(result.errors,[]);
      if(time>=40){
        assert.equal(result.foregroundVisible,false);assert.deepEqual(result.text,[]);
        assert(await page.evaluate(()=>{const pixels=document.getElementById('film').getContext('2d').getImageData(0,0,1920,1080).data;for(let i=3;i<pixels.length;i+=4)if(pixels[i]!==0)return false;return true;}));
      }
      await page.locator('.stage').screenshot({path:path.join(qa,`transition_${String(time).replace('.','_')}.png`)});
    }
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    await page.evaluate(()=>window.seekFilm(2.6));await page.locator('.stage').screenshot({path:path.join(output,'poster.jpg'),type:'jpeg',quality:82});
    await fs.writeFile(path.join(qa,'layout.json'),JSON.stringify({probes,errors,remote},null,2));
    if(!qaOnly)await exportFilm(page,output,work,ffmpeg,timing,qa);
    }
    await page.goto(pathToFileURL(path.join(output,'index.html')).href);await page.waitForFunction(()=>document.querySelector('#video').readyState>=1);
    const metadata=await page.locator('video').evaluate(video=>({duration:video.duration,width:video.videoWidth,height:video.videoHeight}));
    assert(Math.abs(metadata.duration-timing.duration)<.1);assert.equal(metadata.width,1920);assert.equal(metadata.height,1080);
    const frame=page.frameLocator('#deck');await frame.locator('#slide-1').waitFor({state:'attached'});
    await page.locator('#start').click();await page.waitForFunction(()=>!document.querySelector('#video').paused);
    await page.locator('video').evaluate(video=>{video.pause();video.currentTime=40.3;});
    await page.waitForFunction(()=>document.body.classList.contains('foreground-hidden'));assert(!(await page.locator('#skip').isVisible()));
    await page.locator('video').evaluate(video=>{video.currentTime=41.05;});
    await page.waitForFunction(()=>document.body.classList.contains('white-tail'));
    assert.equal(await page.locator('#handoff').evaluate(node=>getComputedStyle(node).opacity),'1');
    assert(!(await page.locator('#cover').isVisible()));await page.screenshot({path:path.join(qa,'player_pure_white.png')});
    await page.locator('video').evaluate(video=>video.play());await page.waitForFunction(()=>document.body.classList.contains('reveal-deck'),{timeout:15000});
    await page.waitForFunction(()=>getComputedStyle(document.getElementById('handoff')).opacity==='0');
    assert(await page.locator('#deck').isVisible());await page.keyboard.press('ArrowRight');assert.equal(await frame.locator('.slide.active').getAttribute('id'),'slide-2');
    await page.screenshot({path:path.join(qa,'player_deck_after_handoff.png')});
    await page.reload();await page.locator('#skip').click();await page.waitForFunction(()=>document.body.classList.contains('reveal-deck'));
    await page.keyboard.press('ArrowRight');assert.equal(await page.frameLocator('#deck').locator('.slide.active').getAttribute('id'),'slide-2');
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    await fs.writeFile(path.join(qa,'verification.json'),JSON.stringify({metadata,timing,layoutProbes:probes.length,transparentTail:true,pureWhiteBeforeHandoff:true,automaticHandoff:true,skipHandoff:true,deckKeyboardNavigation:true,errors,remote},null,2));
    console.log(JSON.stringify({metadata,pureWhiteBeforeHandoff:true,automaticHandoff:true,skipHandoff:true,deckKeyboardNavigation:true}));
  }finally{await browser.close();}
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
