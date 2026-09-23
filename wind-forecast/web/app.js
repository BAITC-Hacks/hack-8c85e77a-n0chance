const $ = id => document.getElementById(id);
let horizon = 48, turbine = 'T1', result = null, busy = false;
const local = value => new Date(value).toLocaleString('ru-RU', {timeZone:'Asia/Almaty', day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'});
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Ошибка запроса');
  return data;
}
async function action(button, work) {
  if(busy) return;
  busy = true; $('error').hidden = true;
  const text = button.textContent;
  document.querySelectorAll('button').forEach(b => b.disabled = true);
  $('upload').disabled = true; button.textContent = 'Выполняется…'; button.classList.add('spinner');
  try { await work(); } catch(error) { $('error').textContent = error.message; $('error').hidden = false; }
  finally { busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false); $('upload').disabled=false; button.textContent=text; button.classList.remove('spinner'); $('export').disabled=!result; }
}
function modeLabel(mode, rows) {
  const demo = mode === 'demo';
  $('modeBanner').querySelector('strong').textContent = demo ? 'Демонстрационный сценарий' : 'Подключены ваши измерения';
  $('modeBanner').children[1].querySelector('span').textContent = demo ? 'Данные синтетические. Точность на реальной ВЭС пока не измерена.' : 'Прогноз использует архив NOAA. Первое скачивание может занять несколько минут.';
  $('rowCount').textContent = `${rows.toLocaleString('ru-RU')} строк · ${demo?'демо':'ваши данные'}`;
  $('update').hidden = !demo;
}
function clearResult() {
  result=null; $('avg').textContent='—'; $('peak').textContent='—'; $('wind').textContent='—'; $('guard').textContent='Готов к проверке';
  $('chart').replaceChildren(); $('agentState').textContent='Ожидание'; $('export').disabled=true;
  $('evaluationBody').textContent='Запустите проверку для текущих данных.';
}
function render(data) {
  result = data;
  horizon = data.horizon;
  $('horizons').querySelectorAll('button').forEach(b=>b.classList.toggle('selected',Number(b.dataset.hours)===horizon));
  $('issue').value = new Date(new Date(data.issue_at).getTime()+5*3600*1000).toISOString().slice(0,16);
  const rows = data.forecasts.filter(r => r.turbine_id === turbine);
  const average = rows.reduce((s,r)=>s+r.power_normalized,0)/rows.length;
  const peak = rows.reduce((a,b)=>a.power_normalized > b.power_normalized ? a : b);
  $('avg').textContent = (average*100).toFixed(1)+' %'; $('peak').textContent=(peak.power_normalized*100).toFixed(1)+' %';
  $('peakTime').textContent=local(peak.valid_at)+' · UTC+5';
  $('wind').textContent=(rows.reduce((s,r)=>s+r.wind_speed_ms,0)/rows.length).toFixed(1)+' м/с';
  $('guard').textContent='Проверено';
  $('agentState').textContent=data.cache_hit ? 'Из кэша' : 'Готово · '+data.fingerprint.slice(0,8);
  $('steps').replaceChildren();
  data.events.forEach((event,i)=>{const li=document.createElement('li'), b=document.createElement('b'), div=document.createElement('div'), title=document.createElement('strong'), p=document.createElement('p'); b.textContent='0'+(i+1); title.textContent=event.step; p.textContent=event.detail; div.append(title,p); li.append(b,div); $('steps').append(li);});
  $('chartDates').textContent=local(rows[0].valid_at)+' — '+local(rows.at(-1).valid_at);
  drawChart(rows); $('export').disabled=false;
}
function svg(tag, attributes, text) { const el=document.createElementNS('http://www.w3.org/2000/svg',tag); Object.entries(attributes).forEach(([k,v])=>el.setAttribute(k,v)); if(text!==undefined)el.textContent=text; return el; }
function drawChart(rows) {
  const chart=$('chart'); chart.replaceChildren();
  const x=i=>52+i/(rows.length-1)*925, y=v=>252-v*222;
  const defs=svg('defs',{}), gradient=svg('linearGradient',{id:'fade',x1:0,y1:0,x2:0,y2:1}); gradient.append(svg('stop',{offset:'0%','stop-color':'#70e6d0','stop-opacity':'.18'}),svg('stop',{offset:'100%','stop-color':'#70e6d0','stop-opacity':'0'}));defs.append(gradient);chart.append(defs);
  for(let p=0;p<=100;p+=25){chart.append(svg('line',{x1:52,x2:977,y1:y(p/100),y2:y(p/100),stroke:'#253344','stroke-dasharray':'3 5'}),svg('text',{x:36,y:y(p/100)+4,'text-anchor':'end',fill:'#8c9fb5','font-size':10},p+'%'));}
  [0,Math.floor(rows.length/4),Math.floor(rows.length/2),Math.floor(rows.length*3/4),rows.length-1].forEach(i=>chart.append(svg('text',{x:x(i),y:281,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle',fill:'#8c9fb5','font-size':10},local(rows[i].valid_at))));
  const points=rows.map((r,i)=>`${x(i)},${y(r.power_normalized)}`);
  chart.append(svg('polygon',{points:`52,252 ${points.join(' ')} 977,252`,fill:'url(#fade)'}));
  const band=rows.map((r,i)=>`${x(i)},${y(r.upper)}`).concat(rows.map((r,i)=>`${x(i)},${y(r.lower)}`).reverse());
  chart.append(svg('polygon',{points:band.join(' '),fill:'#70e6d0','fill-opacity':'.10'}),svg('polyline',{points:points.join(' '),fill:'none',stroke:'#70e6d0','stroke-width':2.5,'stroke-linejoin':'round'}));
  const marker=svg('line',{y1:25,y2:252,stroke:'#668f95','stroke-dasharray':'4 4',visibility:'hidden'});chart.append(marker);
  chart.onpointermove=event=>{const bounds=chart.getBoundingClientRect();const i=Math.max(0,Math.min(rows.length-1,Math.round((((event.clientX-bounds.left)/bounds.width)*1000-52)/925*(rows.length-1))));const row=rows[i];marker.setAttribute('x1',x(i));marker.setAttribute('x2',x(i));marker.setAttribute('visibility','visible');$('tooltip').hidden=false;$('tooltip').textContent=`${local(row.valid_at)} · ${(row.power_normalized*100).toFixed(1)} % · ${row.wind_speed_ms.toFixed(1)} м/с`;};
  chart.onpointerleave=()=>{$('tooltip').hidden=true;marker.setAttribute('visibility','hidden');};
}
async function run(update=false){const value=$('issue').value; if(!value)throw new Error('Выберите дату расчёта'); render(await api('/api/run',{issue:value+':00+05:00',horizon,update}));}
$('run').onclick=()=>action($('run'),()=>run());
$('update').onclick=()=>action($('update'),()=>run(true));
$('horizons').onclick=event=>{if(busy||!event.target.dataset.hours)return;horizon=Number(event.target.dataset.hours);$('horizons').querySelectorAll('button').forEach(b=>b.classList.toggle('selected',Number(b.dataset.hours)===horizon));};
$('turbines').onclick=event=>{if(!event.target.dataset.turbine)return;turbine=event.target.dataset.turbine;$('turbines').querySelectorAll('button').forEach(b=>b.classList.toggle('selected',b.dataset.turbine===turbine));if(result)render(result);};
$('backtest').onclick=()=>action($('backtest'),async()=>{const data=await api('/api/backtest',{}); const table=document.createElement('table');const head=document.createElement('tr');['Турбина / часы','MAE','RMSE','Постоянный прогноз'].forEach(value=>{const cell=document.createElement('th');cell.textContent=value;head.append(cell);});table.append(head);data.metrics.forEach(row=>{const tr=document.createElement('tr');[row.turbine_id+' / '+row.horizon,(row.mae*100).toFixed(2)+' п.п.',(row.rmse*100).toFixed(2)+' п.п.',(row.persistence_mae*100).toFixed(2)+' п.п.'].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});table.append(tr);});$('evaluationBody').classList.remove('evaluation-placeholder');$('evaluationBody').replaceChildren(table);});
$('upload').onchange=()=>action($('run'),async()=>{const file=$('upload').files[0];if(!file)return;if(file.size>19_000_000)throw new Error('Файл должен быть меньше 19 МБ');const data=await api('/api/import',{csv:await file.text()});clearResult();modeLabel(data.mode,data.rows);});
$('demo').onclick=()=>action($('demo'),async()=>{await api('/api/demo',{});clearResult();const data=await api('/api/status');modeLabel(data.mode,data.rows);await run();});
$('export').onclick=()=>{const link=document.createElement('a');link.href='/api/export';link.download='wind-forecast.csv';link.click();};
api('/api/status').then(data=>{modeLabel(data.mode,data.rows);if(data.result)render(data.result);else action($('run'),()=>run());}).catch(error=>{$('error').hidden=false;$('error').textContent=error.message;});
