/* Browser contract for the generated offline presentation; no production database access. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async()=>{
  const target=path.resolve(process.argv[2]);
  const output=path.resolve(process.argv[3] || '.pytest_cache/defense_browser');
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-gpu','--disable-extensions','--no-first-run']});
  try{
    const page=await browser.newPage({viewport:{width:1600,height:964},deviceScaleFactor:1});
    const errors=[],remote=[];
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{if(/^https?:/.test(request.url()))remote.push(request.url());});
    await page.goto(pathToFileURL(target).href);
    await page.waitForFunction(()=>document.documentElement.dataset.fontReady==='true');
    const count=await page.locator('.slide').count();
    assert.equal(count,32);
    const findings=[];
    for(let i=0;i<count;i++){
      await page.evaluate(n=>{location.hash=`slide-${n+1}`;},i);
      await page.waitForFunction(n=>document.querySelector('.slide.active').id===`slide-${n+1}`,i);
      const result=await page.evaluate(()=>{
        const slide=document.querySelector('.slide.active'),box=slide.getBoundingClientRect();
        const bounds=[],walker=document.createTreeWalker(slide,NodeFilter.SHOW_TEXT);
        while(walker.nextNode()){
          const node=walker.currentNode;
          if(!node.textContent.trim()||node.parentElement.closest('style,script,defs,metadata'))continue;
          const range=document.createRange();range.selectNodeContents(node);
          for(const rect of range.getClientRects()){
            if(rect.width===0||rect.height===0)continue;
            const footer=!!node.parentElement.closest('footer,.chart-page');
            if(rect.left<box.left-1||rect.right>box.right+1||rect.top<box.top-1||rect.bottom>box.bottom+1||(!footer&&!node.parentElement.closest('svg')&&rect.bottom>box.top+835)){
              bounds.push({text:node.textContent.slice(0,85),x:Math.round(rect.left-box.left),y:Math.round(rect.top-box.top),right:Math.round(rect.right-box.left),bottom:Math.round(rect.bottom-box.top)});
            }
          }
        }
        const brokenReferences=[...slide.querySelectorAll('svg use')].filter(use=>{
          const ref=use.getAttribute('href')||use.getAttributeNS('http://www.w3.org/1999/xlink','href');
          return !ref||!slide.querySelector(`[id="${ref.slice(1)}"]`);
        }).length;
        return {slide:slide.id,title:slide.dataset.title,overflow:bounds,brokenReferences};
      });
      findings.push(result);
      await page.locator('#stage').screenshot({path:path.join(output,`slide_${String(i+1).padStart(2,'0')}.png`)});
    }
    await page.keyboard.press('Home');assert.equal(await page.locator('.slide.active').getAttribute('id'),'slide-1');
    await page.keyboard.press('ArrowRight');assert.equal(await page.locator('.slide.active').getAttribute('id'),'slide-2');
    await page.keyboard.press('n');assert(await page.locator('#notes').isVisible());
    assert((await page.locator('#notes-body').innerText()).includes('统计口径'));
    await page.keyboard.press('Escape');assert(!(await page.locator('#notes').isVisible()));
    await page.keyboard.press('o');await page.locator('[data-go="14"]').click();
    assert.equal(await page.locator('.slide.active').getAttribute('id'),'slide-15');
    await page.keyboard.press('End');assert.equal(await page.locator('.slide.active').getAttribute('id'),'slide-32');
    assert.equal((await page.locator('.slide.active').innerText()).trim(),'THANKS');
    assert.equal(await page.locator('#slide-32 footer').count(),0);
    assert.equal(await page.locator('template[id^="note-"]').count(),32);
    const glossarySpeech=await page.locator('#note-23').evaluate(node=>node.content.textContent);
    assert(glossarySpeech.includes('Q1')&&glossarySpeech.includes('Q2')&&glossarySpeech.includes('P25')&&glossarySpeech.includes('P50')&&glossarySpeech.includes('IQR'));
    await page.keyboard.press('h');assert(await page.locator('body.chrome-hidden').count());
    await page.keyboard.press('h');assert.equal(await page.locator('body.chrome-hidden').count(),0);
    await page.keyboard.press('f');await page.waitForFunction(()=>!!document.fullscreenElement);
    await page.keyboard.press('f');await page.waitForFunction(()=>!document.fullscreenElement);
    assert.equal(await page.locator('.chart-slide').count(),7);
    assert.equal(await page.locator('svg text').count()>500,true);
    assert.equal(await page.locator('svg image').count(),0);
    assert.equal(await page.locator('#a03-QuadMesh_1 path').count(),168);
    assert.equal(await page.locator('script[src],link[href],img[src^="http"]').count(),0);
    await page.pdf({path:path.join(output,'print_preview.pdf'),preferCSSPageSize:true,printBackground:true});
    await page.setViewportSize({width:390,height:844});
    await page.keyboard.press('Home');
    await page.locator('#stage').screenshot({path:path.join(output,'mobile_cover.png')});
    const mobile=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,scale:parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--scale'))}));
    assert.equal(mobile.scrollWidth,mobile.width);
    const overflow=findings.filter(item=>item.overflow.length);
    const brokenReferences=findings.reduce((sum,item)=>sum+item.brokenReferences,0);
    const summary={slides:count,charts:7,scriptErrors:errors,remoteRequests:remote,mobile,overflow,brokenReferences};
    await fs.writeFile(path.join(output,'browser_checks.json'),JSON.stringify(summary,null,2));
    console.log(JSON.stringify(summary,null,2));
    assert.equal(errors.length,0);assert.equal(remote.length,0);assert.equal(overflow.length,0);
    assert.equal(brokenReferences,0);
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
