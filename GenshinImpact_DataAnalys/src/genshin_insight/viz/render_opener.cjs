/* Deterministic native-canvas motion export; only protected ADS reaches this renderer. */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url'),{spawn}=require('node:child_process'),{chromium}=require('playwright');

async function command(executable,args){
  return new Promise((resolve,reject)=>{const process=spawn(executable,args,{windowsHide:true,stdio:['ignore','ignore','pipe']});let error='';process.stderr.on('data',data=>{error=(error+data.toString()).slice(-6000);});process.on('error',reject);process.on('exit',code=>code===0?resolve(error):reject(new Error(error)));});
}
async function main(){
  const output=path.resolve(process.argv[2]),ffmpeg=process.argv[3],qaOnly=process.argv.includes('--qa-only');
  const qa=path.resolve(__dirname,'../../../.pytest_cache/opener_video_qa');await fs.mkdir(qa,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-extensions','--no-first-run']});
  try{
    const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1}),errors=[],remote=[];
    page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/.test(request.url()))remote.push(request.url());});
    await page.goto(pathToFileURL(path.join(output,'motion.html')).href);await page.waitForFunction(()=>window.filmReady===true);
    const probes=[];
    for(const time of [2.6,6.8,12.9,20.1,26.4,32.4,38]){
      const result=await page.evaluate(t=>window.renderFrame(t),time);probes.push(result);assert.deepEqual(result.errors,[],`Text outside safe area at ${time}`);
      await page.locator('canvas').screenshot({path:path.join(qa,`scene_${result.scene+1}.png`)});
    }
    for(const time of [0,3.98,4,9.98,10,15.98,16,22.98,23,28.98,29,34.98,35,39.966])assert.deepEqual((await page.evaluate(t=>window.renderFrame(t),time)).errors,[]);
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    await page.evaluate(()=>window.renderFrame(2.6));await page.locator('canvas').screenshot({path:path.join(output,'poster.jpg'),type:'jpeg',quality:94});
    await fs.writeFile(path.join(qa,'layout.json'),JSON.stringify({probes,errors,remote},null,2));
    if(qaOnly){console.log(JSON.stringify({layoutProbes:probes.length,errors,remote}));return;}
    if(!qaOnly){
      const raw=path.join(output,'video.h264'),handle=await fs.open(raw,'w');
      try{
        await page.exposeFunction('writeVideoChunk',async value=>{await handle.write(Buffer.from(value,'base64'));});
        await page.exposeFunction('exportProgress',frame=>console.log(`Rendered ${frame}/1200 frames`));
        await page.evaluate(async()=>{
          const config={codec:'avc1.640028',width:1920,height:1080,framerate:30,bitrate:12000000,avc:{format:'annexb'},hardwareAcceleration:'prefer-software'};
          const support=await VideoEncoder.isConfigSupported(config);if(!support.supported)throw new Error('H.264 encoder unavailable');
          let deliveries=Promise.resolve(),failure=null;
          const encoder=new VideoEncoder({output:chunk=>{const bytes=new Uint8Array(chunk.byteLength);chunk.copyTo(bytes);let binary='';for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));const encoded=btoa(binary);deliveries=deliveries.then(()=>window.writeVideoChunk(encoded));},error:error=>{failure=error;}});
          encoder.configure(config);
          for(let frame=0;frame<1200;frame++){
            const result=window.renderFrame(frame/30);if(result.errors.length)throw new Error(JSON.stringify(result.errors));
            const picture=new VideoFrame(document.getElementById('film'),{timestamp:Math.round(frame*1e6/30),duration:Math.round(1e6/30)});
            encoder.encode(picture,{keyFrame:frame%60===0});picture.close();
            if(encoder.encodeQueueSize>5)await new Promise(resolve=>encoder.addEventListener('dequeue',resolve,{once:true}));
            if(frame%120===0){await window.exportProgress(frame);await new Promise(resolve=>setTimeout(resolve,0));}
            if(failure)throw failure;
          }
          await encoder.flush();await deliveries;encoder.close();await window.exportProgress(1200);
        });
      }finally{await handle.close();}
      const target=path.join(output,'开场视频.mp4');
      const encoding=await command(ffmpeg,['-y','-r','30','-i',raw,'-i',path.join(output,'原创配乐.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-af','loudnorm=I=-16:TP=-1.5:LRA=9','-ar','48000','-movflags','+faststart','-t','40',target]);
      await fs.writeFile(path.join(qa,'mux.log'),encoding);await fs.unlink(raw);
      const verification=await command(ffmpeg,['-v','error','-i',target,'-f','null','-']);assert.equal(verification.trim(),'');
      console.log(`Verified MP4: ${target}`);
    }
    await page.goto(pathToFileURL(path.join(output,'index.html')).href);await page.waitForFunction(()=>document.querySelector('#video').readyState>=1);
    const metadata=await page.locator('video').evaluate(video=>({duration:video.duration,width:video.videoWidth,height:video.videoHeight}));
    assert(Math.abs(metadata.duration-40)<.1);assert.equal(metadata.width,1920);assert.equal(metadata.height,1080);
    const frame=page.frameLocator('#deck');await frame.locator('#slide-1').waitFor({state:'attached'});
    await page.locator('#start').click();await page.waitForFunction(()=>!document.querySelector('#video').paused);
    await page.locator('video').evaluate(video=>{video.currentTime=39.8;});await page.waitForFunction(()=>document.body.classList.contains('in-deck'),{timeout:15000});
    assert(await page.locator('#deck').isVisible());await frame.locator('#stage').click();await page.keyboard.press('ArrowRight');assert.equal(await frame.locator('.slide.active').getAttribute('id'),'slide-2');
    await fs.writeFile(path.join(qa,'verification.json'),JSON.stringify({metadata,layoutProbes:probes.length,automaticHandoff:true,deckKeyboardNavigation:true,errors,remote},null,2));
    console.log(JSON.stringify({metadata,automaticHandoff:true,deckKeyboardNavigation:true}));
  }finally{await browser.close();}
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
