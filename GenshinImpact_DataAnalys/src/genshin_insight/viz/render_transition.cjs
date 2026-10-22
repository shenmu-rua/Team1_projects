/* Append the supplied startup wordmark, then match the existing live cover. */
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process'),{once}=require('node:events'),{pathToFileURL}=require('node:url'),{chromium}=require('playwright');
async function command(executable,args){return new Promise((resolve,reject)=>{const child=spawn(executable,args,{windowsHide:true,stdio:['ignore','ignore','pipe']});let log='';child.stderr.on('data',data=>log=(log+data.toString()).slice(-16000));child.on('error',reject);child.on('close',code=>code===0?resolve(log):reject(new Error(log)));});}
async function encode(page,work,source,ffmpeg,duration,sourceDuration){
  const args=['-y','-hide_banner','-f','image2pipe','-framerate','60','-c:v','png','-i','pipe:0','-i',source,'-filter_complex',`[1:a]atrim=0:${sourceDuration},asetpts=PTS-STARTPTS,afade=t=out:st=${sourceDuration-.4}:d=0.4,apad,atrim=duration=${duration}[a]`,'-map','0:v:0','-map','[a]','-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p','-r','60','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-c:a','aac','-b:a','160k','-ar','48000','-t',String(duration),'-map_metadata','-1','-movflags','+faststart',path.join(work,'transition.mp4')];
  const encoder=spawn(ffmpeg,args,{windowsHide:true,stdio:['pipe','ignore','pipe']});let log='',failure=null;
  encoder.stderr.on('data',data=>log=(log+data.toString()).slice(-30000));encoder.stdin.on('error',error=>failure=error);
  const complete=new Promise(resolve=>{encoder.on('error',error=>{failure=error;resolve(-1);});encoder.on('close',resolve);});
  try{const count=Math.round(duration*60);for(let i=0;i<count;i++){
    if(failure)throw failure;
    const png=await page.evaluate(async time=>{await window.renderTransition(time);return document.getElementById('film').toDataURL('image/png').split(',')[1];},i/60);
    if(!encoder.stdin.write(Buffer.from(png,'base64')))await Promise.race([once(encoder.stdin,'drain'),complete.then(()=>{throw new Error(log||'Encoder exited early');})]);
    if(i%60===0)console.log(`Rendered logo transition ${i}/${count}`);
  }encoder.stdin.end();const code=await complete;if(failure||code!==0)throw failure||new Error(log);await fs.writeFile(path.join(work,'encode.log'),log);
  }catch(error){encoder.stdin.destroy();encoder.kill();await complete;throw error;}
}
async function main(){
 const [base,source,deck,work,ffmpeg,sourceSeconds,moveSeconds,holdSeconds]=process.argv.slice(2),sourceDuration=Number(sourceSeconds),moveDuration=Number(moveSeconds),holdDuration=Number(holdSeconds),duration=sourceDuration+moveDuration+holdDuration;
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-extensions','--no-first-run','--allow-file-access-from-files']});
 try{
  const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1}),errors=[],remote=[];page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>{if(/^https?:/.test(request.url()))remote.push(request.url());});
  await page.goto(pathToFileURL(deck).href+'#slide-1');await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const cover=await page.evaluate(()=>{const node=document.querySelector('#slide-1 h1 .genshin-logo');if(!node)throw new Error('The cover wordmark is missing');const r=node.getBoundingClientRect();return {target:{x:r.x,y:r.y,width:r.width,height:r.height},slides:document.querySelectorAll('.slide').length};});
  await page.screenshot({path:path.join(work,'cover.png')});await page.addStyleTag({content:'#slide-1 h1 .genshin-logo{visibility:hidden!important}'});await page.screenshot({path:path.join(work,'cover_without_logo.png')});
  const logo=JSON.parse(await fs.readFile(path.join(__dirname,'genshin_logo.json'),'utf8'));
  const settings={baseUrl:pathToFileURL(base).href,sourceUrl:pathToFileURL(source).href,coverUrl:pathToFileURL(path.join(work,'cover.png')).href,coverWithoutLogoUrl:pathToFileURL(path.join(work,'cover_without_logo.png')).href,logoUrl:pathToFileURL(path.join(__dirname,logo.asset)).href,logoBounds:logo.visible_bounds,target:cover.target,maskY:800,sourceDuration,moveDuration,holdDuration};
  const html=(await fs.readFile(path.join(__dirname,'opener_transition.html'),'utf8')).replace('__SETTINGS__',JSON.stringify(settings).replaceAll('</','<\\/'));await fs.writeFile(path.join(work,'motion.html'),html);
  await page.goto(pathToFileURL(path.join(work,'motion.html')).href);await page.waitForFunction(()=>window.transitionReady===true);
  const baseInfo=await page.evaluate(()=>window.baseInfo);assert.equal(baseInfo.width,1920);assert.equal(baseInfo.height,1080);
  const probes=[];for(const time of [0,.8,1.6,sourceDuration,sourceDuration+.4,sourceDuration+.8,sourceDuration+1.2,sourceDuration+moveDuration,duration-1/60]){
    const result=await page.evaluate(t=>window.renderTransition(t),time);probes.push(result);await page.locator('canvas').screenshot({path:path.join(work,`preview_${time.toFixed(2)}.png`)});
    if(time<sourceDuration)assert(await page.evaluate(()=>{const data=document.getElementById('film').getContext('2d').getImageData(0,800,1920,280).data;for(let i=0;i<data.length;i+=4)if(data[i]!==255||data[i+1]!==255||data[i+2]!==255)return false;return true;}),'Source prompt is still visible');
  }
  assert.deepEqual(probes.at(-1).logo,cover.target);assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
  await encode(page,work,source,ffmpeg,duration,sourceDuration);
  const concat=[base,path.join(work,'transition.mp4')].map(file=>`file '${file.replaceAll('\\','/').replaceAll("'","'\\''")}'`).join('\n');await fs.writeFile(path.join(work,'concat.txt'),concat+'\n');
  await command(ffmpeg,['-y','-hide_banner','-f','concat','-safe','0','-i',path.join(work,'concat.txt'),'-c','copy','-map_metadata','-1','-movflags','+faststart',path.join(work,'combined.mp4')]);
  const decode=await command(ffmpeg,['-v','error','-i',path.join(work,'combined.mp4'),'-f','null','-']);assert.equal(decode.trim(),'');
  const containerDuration=await page.evaluate(async url=>{const video=document.getElementById('base');await new Promise((resolve,reject)=>{video.addEventListener('loadedmetadata',resolve,{once:true});video.addEventListener('error',reject,{once:true});video.src=url;video.load();});return video.duration;},pathToFileURL(path.join(work,'combined.mp4')).href);
  const result={baseDuration:baseInfo.duration,transitionDuration:duration,duration:containerDuration,sourceDuration,moveDuration,holdDuration,sourceBounds:await page.evaluate(()=>window.transitionSourceBounds),target:cover.target,slideCount:cover.slides,maskedPrompt:{y:800,height:280},probes,errors,remote,fullDecodeVerified:true};
  await fs.writeFile(path.join(work,'transition_metadata.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({duration:result.duration,target:result.target,fullDecodeVerified:true}));
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
