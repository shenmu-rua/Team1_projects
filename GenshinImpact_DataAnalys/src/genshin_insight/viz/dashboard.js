/* Offline dashboard: protected aggregates only, no remote requests. */
(() => {
  'use strict';
  const D = JSON.parse(document.getElementById('dashboard-data').textContent);
  const $ = id => document.getElementById(id);
  const E = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = n => Number(n).toLocaleString('en-US');
  const compact = n => n >= 10000 ? (n / 10000).toFixed(1) + '万' : fmt(n);
  const percent = (n, digits = 1) => Number(n).toFixed(digits) + '%';
  const POOLS = [301,302,200,100];
  const NAMES = {100:'新手祈愿',200:'常驻祈愿',301:'角色活动',302:'武器活动'};
  const COLORS = D.display.colors;
  const WEEK = ['周一','周二','周三','周四','周五','周六','周日'];
  const MONTHS = [...new Set(D.months.map(r => r.month))].sort();
  const STAR_TOTAL = D.pools.filter(r => !r.suppressed).reduce((a,r) => a+r.star5,0);
  const state = {pool:'all',start:0,end:MONTHS.length-1,insight:'gap',pinned:null,query:'',ascending:false,tour:false,count:8};
  let resizeFrame, lastFocus, dialogKind = null;
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const poolLabel = () => state.pool === 'all' ? '全部卡池' : NAMES[state.pool];
  const selectedPools = () => state.pool === 'all' ? POOLS : [Number(state.pool)];
  const insightPool = () => state.pool === 'all' ? 301 : Number(state.pool);
  const binsLabel = row => row.hi === null ? `≥${fmt(row.lo)}` : `${fmt(row.lo)}–${fmt(row.hi)}`;
  const tipAttr = (title, lines, note = '') => `data-tip="${E(JSON.stringify({title,lines,note}))}" tabindex="0"`;
  const svg = (w,h,content,label) => `<svg class="chart-svg" viewBox="0 0 ${w} ${h}" role="img" aria-label="${E(label)}">${content}</svg>`;
  const table = (headers,rows) => `<table class="detail-table"><thead><tr>${headers.map(x=>`<th scope="col">${E(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(x=>`<td>${E(x)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const chartBox = html => `<div class="detail-chart">${html}</div>`;
  const announced = message => {$('announcement').textContent = message;};

  function fit() {
    document.documentElement.style.setProperty('--scale',Math.min(innerWidth/1920,innerHeight/1080));
  }
  function showTooltip(target,x,y) {
    const data = JSON.parse(target.dataset.tip);
    const tip = $('tooltip');
    tip.innerHTML = `<strong>${E(data.title)}</strong>${data.lines.map(([key,value])=>`<div class="tip-line"><span>${E(key)}</span><span>${E(value)}</span></div>`).join('')}${data.note?`<small>${E(data.note)}</small>`:''}`;
    tip.hidden=false;
    const box=tip.getBoundingClientRect();
    tip.style.left=Math.max(8,Math.min(innerWidth-box.width-8,x+15))+'px';
    tip.style.top=Math.max(8,Math.min(innerHeight-box.height-8,y+12))+'px';
  }
  function hideTooltip() {$('tooltip').hidden=true;}
  document.addEventListener('pointermove',event=>{
    const target=event.target.closest('[data-tip]');
    if(target) showTooltip(target,event.clientX,event.clientY); else hideTooltip();
  });
  document.addEventListener('pointerleave',hideTooltip);
  document.addEventListener('focusin',event=>{
    const target=event.target.closest('[data-tip]');
    if(target){const box=target.getBoundingClientRect();showTooltip(target,box.left+box.width/2,box.top);}
    else hideTooltip();
  });
  document.addEventListener('focusout',hideTooltip);

  function renderMetrics() {
    const pool=state.pool==='all'?null:D.pools.find(r=>r.pool_group===Number(state.pool));
    const safe=!pool?.suppressed;
    const pulls=pool?(safe?pool.pulls:null):D.scope.pulls;
    const people=pool?(safe?pool.people:null):D.scope.people;
    const stars=pool?(safe?pool.star5:null):STAR_TOTAL;
    const rate=pulls?100*stars/pulls:null;
    const metrics=[
      ['累计留存抽卡记录',pulls===null?'已抑制':fmt(pulls),'抽',state.pool==='all'?'主分析 DS03 · 全部卡池':`${poolLabel()} · 占全局记录 ${percent(100*pulls/D.scope.pulls)}`,'chart'],
      ['贡献账号',people===null?'已抑制':fmt(people),'个',state.pool==='all'?'来源内去重 · 卡池间账号不可相加':'该卡池内去重 · 不代表独立活跃玩家','users'],
      ['五星留存记录',stars===null?'已抑制':fmt(stars),'条','仅统计留存记录内的五星结果','spark'],
      ['记录内五星占比',rate===null?'已抑制':rate.toFixed(2),'%','样本描述性比率 · 不代表官方概率','percent']
    ];
    $('metrics').innerHTML=metrics.map((m,i)=>`<div class="metric ${i===0?'featured ':''}selected-flash"><div class="metric-label">${icon(m[4])}${m[0]}</div><span class="metric-index">0${i+1}</span><div class="metric-value">${m[1]}<small>${m[2]}</small></div><div class="metric-caption">${E(m[3])}</div><svg class="metric-watermark" aria-hidden="true"><use href="#i-${m[4]}"/></svg></div>`).join('');
  }

  function compositionHTML() {
    return [...D.pools].sort((a,b)=>(b.pulls??-1)-(a.pulls??-1)).map(r=>{
      const share=r.suppressed?null:100*r.pulls/D.scope.pulls;
      const active=state.pool===String(r.pool_group);
      return `<button class="pool-row ${active?'selected':''} ${state.pool!=='all'&&!active?'dim':''}" data-select-pool="${r.pool_group}" style="--pool-color:${COLORS[r.pool_group]}" aria-pressed="${active}" aria-label="查看${NAMES[r.pool_group]}数据"><div class="pool-row-top"><i></i><span>${NAMES[r.pool_group]}</span><strong>${share===null?'已抑制':percent(share)}<small>占比</small></strong></div><div class="pool-track"><div class="pool-fill" style="width:${share??0}%"></div></div><div class="pool-row-bottom"><span>${r.suppressed?'小样本保护':fmt(r.pulls)+' 抽'}</span><span>五星记录 <b>${r.suppressed?'已抑制':percent(100*r.star5/r.pulls,2)}</b></span></div></button>`;
    }).join('');
  }
  function renderComposition() {
    const top=D.pools.filter(r=>!r.suppressed).reduce((a,b)=>a.pulls>b.pulls?a:b);
    $('composition-title').textContent=`${NAMES[top.pool_group]}贡献${percent(100*top.pulls/D.scope.pulls)}`;
    $('composition').innerHTML=compositionHTML();
  }

  function monthlyRows(){return D.months.filter(r=>selectedPools().includes(r.pool_group)&&r.month>=MONTHS[state.start]&&r.month<=MONTHS[state.end]);}
  function monthPeak(){return monthlyRows().filter(r=>!r.suppressed&&r.pulls!==null).sort((a,b)=>b.pulls-a.pulls)[0];}
  function niceMax(value){const magnitude=10**Math.floor(Math.log10(value||1));return Math.ceil(value/magnitude/0.25)*magnitude*0.25;}
  function trendSVG(w=1080,h=195){
    const months=MONTHS.slice(state.start,state.end+1), rows=monthlyRows();
    const max=niceMax(Math.max(1,...rows.filter(r=>!r.suppressed&&r.pulls!==null).map(r=>r.pulls)));
    const m={left:57,right:19,top:17,bottom:28},cw=w-m.left-m.right,ch=h-m.top-m.bottom;
    const x=i=>m.left+(months.length===1?cw/2:i*cw/(months.length-1));
    const y=v=>m.top+ch*(1-v/max);
    let body='<defs>';
    for(const pool of selectedPools())body+=`<linearGradient id="trend-fill-${pool}-${w}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${COLORS[pool]}" stop-opacity=".15"/><stop offset="1" stop-color="${COLORS[pool]}" stop-opacity=".01"/></linearGradient>`;
    body+='</defs>';
    for(let i=0;i<=4;i++){const value=max*i/4;body+=`<line class="${i===0?'zero-line':'grid-line'}" x1="${m.left}" y1="${y(value)}" x2="${w-m.right}" y2="${y(value)}"/><text class="axis-text" x="${m.left-10}" y="${y(value)+4}" text-anchor="end">${value>=10000?(value/10000).toFixed(value%10000?1:0)+'万':fmt(Math.round(value))}</text>`;}
    body+=`<text class="axis-text" x="${m.left}" y="10">抽</text>`;
    months.forEach((month,i)=>{
      if(months.length<13||i%2===0||i===months.length-1) body+=`<text class="axis-text" x="${x(i)}" y="${h-5}" text-anchor="middle">${months.length<=8?month:month.slice(2).replace('-','/')}</text>`;
    });
    if(state.pinned&&months.includes(state.pinned)){const px=x(months.indexOf(state.pinned));body+=`<line class="hover-line" x1="${px}" y1="${m.top}" x2="${px}" y2="${h-m.bottom}"/>`;}
    const segments=[];
    for(const pool of selectedPools()){
      let segment=[];const chunks=[];
      months.forEach((month,i)=>{
        const row=rows.find(r=>r.month===month&&r.pool_group===pool);
        if(row&&!row.suppressed&&row.pulls!==null) segment.push({x:x(i),y:y(row.pulls),row});
        else if(segment.length){chunks.push(segment);segment=[];}
      });
      if(segment.length)chunks.push(segment);
      chunks.forEach(points=>{
        const path=points.map((p,i)=>`${i?'L':'M'}${p.x},${p.y}`).join(' ');
        if(selectedPools().length===1&&points.length>1)body+=`<path d="${path} L${points.at(-1).x},${y(0)} L${points[0].x},${y(0)} Z" fill="url(#trend-fill-${pool}-${w})"/>`;
        body+=`<path class="data-line" d="${path}" stroke="${COLORS[pool]}"/>`;
        points.forEach(p=>{body+=`<circle cx="${p.x}" cy="${p.y}" r="${state.pinned===p.row.month?4:2.6}" fill="${COLORS[pool]}" stroke="white" stroke-width="1.1"/>`;segments.push({...p,pool});});
      });
    }
    for(const p of segments)body+=`<circle class="point-hit" cx="${p.x}" cy="${p.y}" r="8" style="--point-color:${COLORS[p.pool]}" data-month="${p.row.month}" ${tipAttr(p.row.month+' · '+NAMES[p.pool],[['留存记录',fmt(p.row.pulls)+' 抽'],['贡献账号下界','≥ '+fmt(p.row.people)+' 个']],'点击固定该月；时区与完整性未知')} aria-label="${p.row.month} ${NAMES[p.pool]} ${fmt(p.row.pulls)}抽"/>`;
    if(!segments.length)body+=`<text x="${w/2}" y="${h/2}" text-anchor="middle">所选范围暂无可发布月度记录</text>`;
    return svg(w,h,body,'月度留存记录，单纵轴从0开始；隐藏月份保留缺口');
  }
  function renderTrendReading(){
    if(state.pinned){
      const rows=monthlyRows().filter(r=>r.month===state.pinned);
      $('trend-reading').innerHTML=`<span class="reading-label">已固定 ${E(state.pinned)}</span>${rows.map(r=>`<span>${NAMES[r.pool_group]} <strong>${r.suppressed||r.pulls===null?'已抑制':compact(r.pulls)+'抽'}</strong></span>`).join('')}<span>点击其他月份切换</span>`;
    }else{
      const peak=monthPeak();
      $('trend-reading').innerHTML=peak?`<span class="reading-label">区间峰值</span><span>${peak.month} · ${NAMES[peak.pool_group]}</span><strong>${compact(peak.pulls)} 抽</strong><span>悬停读数 · 点击月份固定</span>`:'<span>所选范围无可发布记录；隐藏格不视为0。</span>';
    }
  }
  function renderTrend(){
    const peak=monthPeak();
    $('trend-title').textContent=peak?`${peak.month} 单池月记录达 ${compact(peak.pulls)} 抽`:'所选区间无可发布月度记录';
    $('trend-scope').textContent=poolLabel();
    $('trend-legend').innerHTML=selectedPools().map(p=>`<span><i style="--dot:${COLORS[p]}"></i>${NAMES[p]}</span>`).join('');
    $('trend').innerHTML=trendSVG();
    $('month-start').value=state.start;$('month-end').value=state.end;
    document.querySelectorAll('[data-range]').forEach(button=>button.classList.toggle('active',button.dataset.range==='all'?state.start===0&&state.end===MONTHS.length-1:state.end===MONTHS.length-1&&state.end-state.start+1===Number(button.dataset.range)));
    renderTrendReading();
  }

  function volumeHTML(){
    const max=Math.max(...D.volume_bins.map(r=>r.counts[0]));
    return D.volume_bins.map(r=>{
      const value=r.counts[0];
      return `<div class="volume-row ${value===max?'peak':''}" ${tipAttr(binsLabel(r)+' 抽/账号',[['账号数',fmt(value)+' 个'],['占全局账号',percent(100*value/D.scope.people)]],'区间是安全合并的分类分箱，条长表示账号数')}><span class="volume-label">${E(binsLabel(r))}</span><div class="volume-track"><div class="volume-fill" style="width:${100*value/max}%"></div></div><span class="volume-value">${fmt(value)}</span></div>`;
    }).join('');
  }
  function renderVolume(){
    $('volume-median').textContent=fmt(D.volume_median);
    $('volume').innerHTML=volumeHTML();
  }
  function blend(a,b,t){const rgb=hex=>hex.match(/\w\w/g).map(v=>parseInt(v,16));const aa=rgb(a.replace('#','')),bb=rgb(b.replace('#',''));return '#'+aa.map((v,i)=>Math.round(v+(bb[i]-v)*t).toString(16).padStart(2,'0')).join('');}
  function heatColor(ratio){const [light,main,dark]=D.display.heat_palette;const value=Math.sqrt(ratio);return value<.65?blend(light,main,value/.65):blend(main,dark,(value-.65)/.35);}
  function heatmapSVG(w=660,h=175){
    const max=Math.max(...D.clock.filter(r=>!r.suppressed&&r.pulls!==null).map(r=>r.pulls));
    const m={left:32,right:0,top:17,bottom:4},cw=(w-m.left)/24,ch=(h-m.top-m.bottom)/7;
    let body='';
    for(let hour=0;hour<24;hour+=2)body+=`<text class="axis-text" x="${m.left+(hour+.5)*cw}" y="10" text-anchor="middle">${String(hour).padStart(2,'0')}</text>`;
    for(let day=0;day<7;day++)body+=`<text class="axis-text" x="0" y="${m.top+(day+.5)*ch+3.5}">${WEEK[day]}</text>`;
    for(const row of D.clock){
      const hidden=row.suppressed||row.pulls===null,x=m.left+row.hour*cw,y=m.top+row.weekday*ch;
      const value=hidden?'—':(row.pulls/10000).toFixed(row.pulls>=100000?0:row.pulls>=1000?1:2);
      const ratio=hidden?0:row.pulls/max;
      body+=`<g ${tipAttr(WEEK[row.weekday]+' '+String(row.hour).padStart(2,'0')+':00–'+String(row.hour).padStart(2,'0')+':59',[['累计留存',hidden?'已抑制':fmt(row.pulls)+' 抽'],['贡献账号',hidden?'已抑制':fmt(row.people)+' 个']],'全局聚合；时区与曝光天数未知')}><rect class="heat-cell" x="${x}" y="${y}" width="${cw}" height="${ch}" rx="3" fill="${hidden?'#e6eef8':heatColor(ratio)}"/><text x="${x+cw/2}" y="${y+ch/2+3.5}" text-anchor="middle" style="fill:${ratio>.35?'#ffffff':'#503047'};font-size:11px;pointer-events:none">${value}</text></g>`;
    }
    return svg(w,h,body,'全局星期小时累计抽数矩阵，粉色越深表示记录越多');
  }
  function renderHeatmap(){
    const peak=D.clock.filter(r=>!r.suppressed&&r.pulls!==null).sort((a,b)=>b.pulls-a.pulls)[0];
    $('heatmap-title').textContent=`${WEEK[peak.weekday]}${peak.hour}时留存最多 · ${compact(peak.pulls)}抽`;
    $('heatmap').innerHTML=heatmapSVG();
    $('heatmap-max').textContent=compact(peak.pulls);
  }

  function gapSVG(pool,w=370,h=128){
    const bins=D.gap_bins[pool];
    if(!bins?.length)return `<div class="empty-state">${icon('spark')}<p>新手池未发布相邻五星间隔</p><button data-switch-rate="true">查看账号分组占比 →</button></div>`;
    const total=bins.reduce((a,r)=>a+r.counts[pool],0),max=niceMax(Math.max(...bins.map(r=>100*r.counts[pool]/total)));
    const m={left:32,right:5,top:10,bottom:26},cw=(w-m.left-m.right)/bins.length,ch=h-m.top-m.bottom;
    let body='';
    for(let i=0;i<=2;i++){const v=max*i/2,y=m.top+ch*(1-v/max);body+=`<line class="${i?'grid-line':'zero-line'}" x1="${m.left}" x2="${w-m.right}" y1="${y}" y2="${y}"/><text class="axis-text" x="${m.left-6}" y="${y+3}" text-anchor="end">${v.toFixed(0)}%</text>`;}
    bins.forEach((row,i)=>{
      const value=row.counts[pool],share=100*value/total,barH=share/max*ch,x=m.left+i*cw+cw*.18,y=m.top+ch-barH;
      const label=row.hi===null?`${row.lo}+`:row.hi;
      body+=`<rect x="${x}" y="${y}" width="${cw*.64}" height="${Math.max(.5,barH)}" rx="2" fill="${COLORS[pool]}" opacity="${share>40?1:.68}" ${tipAttr(binsLabel(row)+' 条记录间隔',[['闭合间隔',fmt(value)+' 段'],['占该池可发布间隔',percent(share)],['贡献账号下界','≥ '+fmt(row.people[pool])+' 个']],'区间可能合并；横轴按分类等宽排列')} /><text class="axis-text" x="${x+cw*.32}" y="${h-9}" text-anchor="middle">${label}</text>`;
    });
    return svg(w,h,body,NAMES[pool]+'相邻已记录五星间隔分箱，纵轴表示间隔占比');
  }
  function rateSVG(pool,w=370,h=128){
    const rows=D.rates.filter(r=>r.pool_group===pool),max=Math.max(1,...rows.map(r=>r.q75))*1.1;
    const m={left:37,right:45,top:4,bottom:22},cw=w-m.left-m.right,ch=h-m.top-m.bottom;
    const x=v=>m.left+cw*v/max;
    let body='';
    for(let i=0;i<=3;i++){const v=max*i/3;body+=`<line class="grid-line" x1="${x(v)}" y1="${m.top}" x2="${x(v)}" y2="${h-m.bottom}"/><text class="axis-text" x="${x(v)}" y="${h-4}" text-anchor="middle">${v.toFixed(1)}%</text>`;}
    rows.forEach((r,i)=>{const y=m.top+(i+.5)*ch/rows.length,label=r.groups===1?'单组':'Q'+r.quartile;
      body+=`<g ${tipAttr(NAMES[pool]+' · '+label,[['账号数',fmt(r.people)+' 个'],['中位数 P50',percent(r.median,2)],['下四分位 P25',percent(r.q25,2)],['上四分位 P75',percent(r.q75,2)]],'各池内按账号抽数分组；账号等权；区间不是置信区间')}><text x="0" y="${y+3}">${label}</text><line x1="${x(r.q25)}" x2="${x(r.q75)}" y1="${y}" y2="${y}" stroke="${COLORS[pool]}" stroke-width="7" opacity=".25" stroke-linecap="round"/><line x1="${x(r.q25)}" x2="${x(r.q25)}" y1="${y-6}" y2="${y+6}" stroke="${COLORS[pool]}"/><line x1="${x(r.q75)}" x2="${x(r.q75)}" y1="${y-6}" y2="${y+6}" stroke="${COLORS[pool]}"/><circle cx="${x(r.median)}" cy="${y}" r="4" fill="${COLORS[pool]}"/><text x="${w-1}" y="${y+3}" text-anchor="end" style="fill:${COLORS[pool]}">${r.median.toFixed(2)}%</text></g>`;
    });
    return svg(w,h,body,'账号记录量分组的五星占比中位数与四分位区间');
  }
  function insightReading(){
    const pool=insightPool();
    if(state.insight==='rate'){
      const rows=D.rates.filter(r=>r.pool_group===pool),last=rows.at(-1);
      return last?`${last.groups===1?'单组':'Q'+last.quartile+'组'}五星占比中位 <strong>${percent(last.median,2)}</strong>`:'暂无可发布账号分组';
    }
    const bins=D.gap_bins[pool];
    if(!bins?.length)return '首段与未闭合尾段不进入间隔统计';
    const total=bins.reduce((a,r)=>a+r.counts[pool],0),peak=bins.reduce((a,b)=>a.counts[pool]>b.counts[pool]?a:b);
    return `${binsLabel(peak)}条区间占 <strong>${percent(100*peak.counts[pool]/total)}</strong>`;
  }
  function renderInsight(){
    const pool=insightPool();
    $('insight-scope').textContent=NAMES[pool]+(state.pool==='all'?' · 默认':'');
    $('insight').innerHTML=state.insight==='gap'?gapSVG(pool):rateSVG(pool);
    $('insight-reading').innerHTML=insightReading();
    $('insight-note').textContent=state.insight==='gap'?'首段与未闭合尾段已排除；横轴为分箱上限（条），区间等宽排列。不能推断保底。':'Q组按池内账号抽数分组；点为账号等权中位数，线为P25–P75；不是置信区间。';
    document.querySelectorAll('[data-insight]').forEach(button=>{const active=button.dataset.insight===state.insight;button.classList.toggle('active',active);button.setAttribute('aria-pressed',active);});
  }

  function renderNames(){
    const query=state.query.trim().toLocaleLowerCase();
    const rows=D.items.filter(r=>r.name.toLocaleLowerCase().includes(query)).sort((a,b)=>state.ascending?a.pulls-b.pulls:b.pulls-a.pulls);
    const max=Math.max(...D.items.map(r=>r.pulls));
    $('rank-count').textContent=query?`${rows.length} / ${D.items.length} 个名称`:`${D.items.length} 个原始名称`;
    $('rank-sort').textContent='记录数 '+(state.ascending?'↑':'↓');
    $('rank-sort').setAttribute('aria-label',state.ascending?'按记录数从高到低排序':'按记录数从低到高排序');
    $('names').innerHTML=rows.length?rows.map(row=>{
      const rank=[...D.items].sort((a,b)=>b.pulls-a.pulls).findIndex(r=>r.name===row.name)+1;
      return `<li class="name-row" ${tipAttr(row.name,[['五星记录',fmt(row.pulls)+' 条'],['占全部五星',percent(100*row.pulls/STAR_TOTAL)],['贡献账号下界','≥ '+fmt(row.people)+' 个']],'精确原始名称；不合并别名；不是人气榜')}><span class="name-index">${String(rank).padStart(2,'0')}</span><div class="name-main"><div class="name-label">${E(row.name)}</div><div class="name-bar"><i style="width:${100*row.pulls/max}%"></i></div></div><span class="name-number">${fmt(row.pulls)}</span></li>`;
    }).join(''):'<li class="names-empty">前12个原始名称中没有匹配结果</li>';
  }

  function renderAll(){
    document.querySelectorAll('[data-pool]').forEach(button=>{const active=button.dataset.pool===state.pool;button.classList.toggle('active',active);button.setAttribute('aria-pressed',active);});
    renderMetrics();renderComposition();renderTrend();renderInsight();
    if(dialogKind&&dialogKind!=='method')renderDetail(dialogKind);
  }
  function stopTour(){
    state.tour=false;state.count=8;updateTour();
  }
  function selectPool(pool,manual=true){
    if(pool!=='all'&&!POOLS.includes(Number(pool)))return;
    if(manual)stopTour();
    state.pool=String(pool);state.pinned=null;hideTooltip();renderAll();
    announced(`已切换至${poolLabel()}，规模、月度趋势与五星观察已更新。`);
  }
  function updateTour(){
    const button=$('tour-button');
    button.setAttribute('aria-pressed',state.tour);
    button.innerHTML=icon(state.tour?'pause':'play')+`<span>${state.tour?'暂停轮播':'自动轮播'}</span><small id="tour-count">${state.tour?state.count:8}s</small>`;
  }
  function reset(){
    stopTour();Object.assign(state,{pool:'all',start:0,end:MONTHS.length-1,insight:'gap',pinned:null,query:'',ascending:false});
    $('name-search').value='';renderAll();renderNames();announced('所有筛选已复位。');
  }

  function methodHTML(){
    return `<div class="method-grid"><section class="method-card"><h3>统计范围</h3><p>主分析数据集 DS03，<strong>${fmt(D.scope.people)}个账号、${fmt(D.scope.pulls)}条记录</strong>。记录范围 ${E(D.scope.first_time)} 至 ${E(D.scope.last_time)}，时区未知。账号仅在来源内去重；样本由公开、留存与自选择共同形成。</p></section><section class="method-card"><h3>筛选如何联动</h3><p>卡池选择联动关键规模、月度趋势与五星观察。<strong>月份范围仅影响月度趋势</strong>。星期小时矩阵、账号分布与名称榜为全局聚合，保持全局统计。全池视图的五星观察默认展示角色活动池。</p></section><section class="method-card"><h3>小样本与缺失</h3><p>发布门槛为<strong>至少${D.privacy.minimum_people}个贡献账号</strong>，不足门槛的格子与互补抑制格保持空值，不能补零或用总量回推。月份、名称与间隔分箱的贡献人数是保守下界。缺失月份不插值，起止月可能不完整。</p></section><section class="method-card"><h3>五星记录的解释边界</h3><p>五星占比与间隔描述所提供记录，<strong>不能替代官方概率或保底规则</strong>。间隔排除首段与未闭合尾段；分组区间为P25–P75，不是置信区间。名称保留原始写法，不合并别名；记录量不换算消费或活跃。</p></section></div><p class="detail-note">操作：点击卡池或构成条联动；月度点可点击固定；图表悬停或键盘聚焦显示数值。F 全屏，P 卡池轮播，R 复位，Esc 关闭详情。页面可离线运行，数据时段为历史归档。</p><div class="method-provenance">聚合配置 ${E(D.provenance.config_version)} · 清洗规则 ${E(D.provenance.rule_version)} · 大屏 ${E(D.display.version)}<br>来源校验 SHA-256：${E(D.display.ads_sha256)}</div>`;
  }
  function renderDetail(kind){
    dialogKind=kind;
    const content=$('dialog-content');
    if(kind==='method'){$('dialog-title').textContent='数据口径与阅读方式';content.innerHTML=methodHTML();return;}
    const notes={
      composition:'卡池构成以主分析总抽数为分母。各池贡献账号可能重叠，不能相加为独立人数。角色活动301/400合并，颜色在所有图表保持一致。',
      trend:'按原始时间的自然月统计；各卡池共用从0开始的纵轴。抑制格与缺失格均显示为缺口，不能从全量回推。月份范围只影响本图；账号数为贡献人数保守下界。',
      volume:'账号在DS03来源内去重并合并其各池记录。区间按安全规则合箱，横条按分类等宽排列，条长表示账号数，不是等宽直方图。',
      heatmap:'全局7×24累计记录，时区和每个时段的曝光天数未知，数值不代表归一化的日常活跃程度。数字是累计抽数，采用单粉色阶。',
      insight:state.insight==='gap'?'只统计同一账号、同一卡池内相邻已记录五星的序号差，排除首个五星前段和未闭合尾段；无法识别缺失历史。分箱宽度可能不同，按分类等宽排列，纵轴表示间隔占比，不推算概率或保底。':'按各池账号抽数进行分组；重复边界可能合并。点为账号等权的五星占比中位数，线为P25到P75四分位区间；不是置信区间。'
    };
    let chart='',rows=[],headers=[];
    if(kind==='composition'){
      $('dialog-title').textContent='卡池留存记录构成';chart=`<div class="composition">${compositionHTML()}</div>`;
      headers=['卡池','留存抽数','全局占比','五星记录','五星占比'];rows=D.pools.map(r=>[NAMES[r.pool_group],r.suppressed?'已抑制':fmt(r.pulls),r.suppressed?'已抑制':percent(100*r.pulls/D.scope.pulls),r.suppressed?'已抑制':fmt(r.star5),r.suppressed?'已抑制':percent(100*r.star5/r.pulls,2)]);
    }else if(kind==='trend'){
      $('dialog-title').textContent=`${poolLabel()} · ${MONTHS[state.start]}—${MONTHS[state.end]}`;chart=trendSVG(1060,375);
      headers=['月份','卡池','留存抽数','贡献账号下界'];rows=monthlyRows().map(r=>[r.month,NAMES[r.pool_group],r.suppressed||r.pulls===null?'已抑制':fmt(r.pulls),r.suppressed||r.people===null?'已抑制':'≥ '+fmt(r.people)]);
    }else if(kind==='volume'){
      $('dialog-title').textContent=`账号留存抽数中位 ${fmt(D.volume_median)} 抽`;chart=`<div class="volume-chart">${volumeHTML()}</div>`;
      headers=['账号抽数区间','账号数','占全局账号'];rows=D.volume_bins.map(r=>[binsLabel(r),fmt(r.counts[0]),percent(100*r.counts[0]/D.scope.people)]);
    }else if(kind==='heatmap'){
      $('dialog-title').textContent='全局星期 × 小时累计留存记录（格内单位：万抽）';chart=heatmapSVG(1060,375);
      headers=['星期','小时','累计留存抽数','贡献账号'];rows=D.clock.map(r=>[WEEK[r.weekday],`${r.hour}:00–${r.hour}:59`,r.suppressed?'已抑制':fmt(r.pulls),r.suppressed?'已抑制':fmt(r.people)]);
    }else if(kind==='insight'){
      const pool=insightPool();$('dialog-title').textContent=`${NAMES[pool]} · ${state.insight==='gap'?'相邻五星间隔':'账号分组五星占比'}`;
      chart=state.insight==='gap'?gapSVG(pool,1060,375):rateSVG(pool,1060,375);
      if(state.insight==='gap'){
        const bins=D.gap_bins[pool]||[],total=bins.reduce((sum,r)=>sum+r.counts[pool],0);
        headers=['间隔区间（条）','闭合间隔数','占可发布间隔','贡献账号下界'];rows=bins.map(r=>[binsLabel(r),fmt(r.counts[pool]),percent(100*r.counts[pool]/total),'≥ '+fmt(r.people[pool])]);
      }else{
        headers=['抽数分组','账号数','P25','中位数 P50','P75'];rows=D.rates.filter(r=>r.pool_group===pool).map(r=>[r.groups===1?'单组':'Q'+r.quartile,fmt(r.people),percent(r.q25,2),percent(r.median,2),percent(r.q75,2)]);
      }
    }
    content.innerHTML=chartBox(chart)+`<p class="detail-note">${E(notes[kind])}</p>`+table(headers,rows);
  }
  function openDialog(kind){
    hideTooltip();stopTour();lastFocus=document.activeElement;renderDetail(kind);$('detail-dialog').showModal();
    $('detail-dialog').scrollTop=0;$('dialog-close').focus();
  }
  function closeDialog(){$('detail-dialog').close();}
  $('detail-dialog').addEventListener('close',()=>{dialogKind=null;hideTooltip();lastFocus?.focus();});
  $('detail-dialog').addEventListener('click',e=>{if(e.target===$('detail-dialog')){const b=$('detail-dialog').getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)closeDialog();}});
  $('dialog-close').addEventListener('click',closeDialog);

  async function fullscreen(){
    try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}
    catch{announced('此浏览器未允许全屏，可使用浏览器的全屏功能。');}
  }
  document.addEventListener('fullscreenchange',()=>{
    $('fullscreen-button').querySelector('span').textContent=document.fullscreenElement?'退出全屏':'全屏展示';fit();
  });
  $('fullscreen-button').addEventListener('click',fullscreen);
  $('help-button').addEventListener('click',()=>openDialog('method'));
  $('method-button').addEventListener('click',()=>openDialog('method'));
  $('reset-button').addEventListener('click',reset);
  $('tour-button').addEventListener('click',()=>{state.tour=!state.tour;state.count=8;updateTour();});
  document.addEventListener('click',event=>{
    const pool=event.target.closest('[data-pool],[data-select-pool]');
    if(pool){selectPool(pool.dataset.pool??pool.dataset.selectPool);return;}
    const range=event.target.closest('[data-range]');
    if(range){stopTour();state.end=MONTHS.length-1;state.start=range.dataset.range==='all'?0:Math.max(0,MONTHS.length-Number(range.dataset.range));state.pinned=null;renderTrend();return;}
    const insight=event.target.closest('[data-insight]');
    if(insight){stopTour();state.insight=insight.dataset.insight;renderInsight();return;}
    const switchRate=event.target.closest('[data-switch-rate]');
    if(switchRate){state.insight='rate';renderInsight();if(dialogKind==='insight')renderDetail('insight');return;}
    const expand=event.target.closest('[data-expand]');if(expand){openDialog(expand.dataset.expand);return;}
    const point=event.target.closest('[data-month]');
    if(point){state.pinned=point.dataset.month;renderTrend();if(dialogKind==='trend')renderDetail('trend');return;}
  });
  function updateRange(which,value){
    stopTour();state[which]=Number(value);if(state.start>state.end){if(which==='start')state.end=state.start;else state.start=state.end;}
    state.pinned=null;hideTooltip();renderTrend();
  }
  $('month-start').addEventListener('change',e=>updateRange('start',e.target.value));
  $('month-end').addEventListener('change',e=>updateRange('end',e.target.value));
  $('name-search').addEventListener('input',e=>{stopTour();state.query=e.target.value;renderNames();hideTooltip();});
  $('rank-sort').addEventListener('click',()=>{state.ascending=!state.ascending;renderNames();});
  document.addEventListener('keydown',event=>{
    if(event.target.matches('input,select,textarea')||event.ctrlKey||event.metaKey||event.altKey)return;
    if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-month]')){event.preventDefault();state.pinned=event.target.dataset.month;renderTrend();if(dialogKind==='trend')renderDetail('trend');return;}
    if(event.key==='Escape'){hideTooltip();return;}
    if($('detail-dialog').open)return;
    if(event.key.toLowerCase()==='f'){event.preventDefault();fullscreen();}
    if(event.key.toLowerCase()==='p'){event.preventDefault();$('tour-button').click();}
    if(event.key.toLowerCase()==='r'){event.preventDefault();reset();}
    if(event.key==='/'){event.preventDefault();$('name-search').focus();}
  });
  window.addEventListener('resize',()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(fit);});
  function clock(){
    const now=new Date();$('clock-time').textContent=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(now);
    $('clock-date').textContent=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(now)+' · 展示时间';
  }
  setInterval(()=>{
    clock();
    if(!state.tour||document.hidden||$('detail-dialog').open)return;
    state.count--;
    if(state.count<=0){const order=['all','301','302','200','100'];selectPool(order[(order.indexOf(state.pool)+1)%order.length],false);state.count=8;}
    $('tour-count').textContent=state.count+'s';
  },1000);
  MONTHS.forEach((month,i)=>{for(const name of ['month-start','month-end'])$(name).add(new Option(month,i));});
  $('top-share').innerHTML=(100*D.items.reduce((a,r)=>a+r.pulls,0)/STAR_TOTAL).toFixed(1)+'<span>%</span>';
  $('names-count').textContent=D.items.length;
  $('name-search').placeholder=`搜索前${D.items.length}个原始名称`;
  $('source-period').textContent=D.scope.first_time.slice(0,10).replaceAll('-','.')+' — '+D.scope.last_time.slice(0,10).replaceAll('-','.');
  $('source-version').textContent=`聚合 ${D.provenance.config_version} · 规则 ${D.provenance.rule_version}`;
  fit();clock();renderAll();renderVolume();renderHeatmap();renderNames();
})();
