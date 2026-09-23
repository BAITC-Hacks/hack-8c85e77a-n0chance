import {Miniflare} from 'miniflare';
import {readFileSync,readdirSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import ts from 'typescript';
import assert from 'node:assert/strict';
const moduleFiles=readdirSync('dist/server',{recursive:true}).filter(p=>p.endsWith('.js')&&p!=='index.js');
const mf=new Miniflare({modules:['index.js',...moduleFiles].map(path=>({type:'ESModule',path:resolve('dist/server',path),contents:readFileSync(resolve('dist/server',path),'utf8')})),modulesRoot:resolve('dist/server'),compatibilityDate:'2026-05-15',compatibilityFlags:['nodejs_compat'],d1Databases:{DB:'workflow-test'},cf:false});
let passed=0;
try{
 const db=await mf.getD1Database('DB');
 for(const file of readdirSync('drizzle').filter(f=>f.endsWith('.sql')).sort())for(const sql of readFileSync('drizzle/'+file,'utf8').split('--> statement-breakpoint').map(x=>x.trim()).filter(Boolean))await db.prepare(sql).run();
 async function request(user,body,status=200){const headers={Origin:'http://localhost'};if(user){headers['oai-authenticated-user-id']=user;headers['oai-authenticated-user-email']=user+'@example.test'}if(body)headers['Content-Type']='application/json';const r=await mf.dispatchFetch('http://localhost/api/platform',{method:body?'POST':'GET',headers,...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();assert.equal(r.status,status,JSON.stringify(data));passed++;return data}
 const full={title:'Прогноз продаж для пекарни',category:'Аналитика',problem:'Каждый вечер остаётся непроданная выпечка. Объёмы производства пока определяются на глаз.',need:'Снизить списания и прогнозировать спрос.',users:'Управляющий и пекари смены',result:'Модель прогноза продаж и отчёт для управляющего.',metric:'Снижение списаний на 20 процентов.',resources:'История продаж за год и консультация управляющего.',constraints:'Пилот за четыре недели на обезличенных данных.',contact:'business@example.test',interaction:'Созвон по вторникам и проверка промежуточного отчёта.',deadline:'2099-12-01',reward:'Учебный проект без оплаты',confirmed:true};
 await request(null,{action:'profile',role:'business',name:'Аноним'},401);
 await request('biz',{action:'profile',role:'business',name:'Тестовый бизнес'});
 await request('other',{action:'profile',role:'business',name:'Другой бизнес'});
 for(const id of ['team1','team2','team3'])await request(id,{action:'profile',role:'team',name:id,university:'Тестовый университет',skills:'Аналитика и разработка'});
 await request('biz',{action:'saveTask',...full,confirmed:false,publish:true},400);
 await request('biz',{action:'saveTask',...full,deadline:'2026-99-99',publish:true},400);
 const draft=await request('biz',{action:'saveTask',...full,confirmed:false,publish:false});
 assert.equal(draft.score,0);passed++;
 assert.equal((await request('team1')).tasks.length,0);passed++;
 await request('other',{action:'saveTask',id:draft.id,...full,publish:true},404);
 const high=await request('biz',{action:'saveTask',id:draft.id,...full,publish:true});assert.equal(high.score,100);passed++;
 const low=await request('biz',{action:'saveTask',title:'Нужен сайт',category:'Разработка',problem:'Сделать сайт',confirmed:true,publish:true});assert.equal(low.score,0);passed++;
 const catalog=await request(null);assert.equal(catalog.tasks.length,2);assert.equal(catalog.tasks[0].id,high.id);passed+=2;
 await request('team1',{action:'saveTask',...full,publish:true},403);
 await request('biz',{action:'saveTask',id:low.id,...full,publish:true});
 const updated=(await request(null)).tasks.find(t=>t.id===low.id);assert.equal(updated.need,full.need);passed++;
 const weakAi=await request('biz',{action:'clarify',description:'Нужен сайт',fields:{category:'Разработка'}});assert.ok(weakAi.questions.length>=3);assert.equal(weakAi.draft.result,'');assert.equal(weakAi.draft.problem,'Нужен сайт');passed+=3;
 const proposal={action:'propose',task:draft.id,approach:'Построим прогноз спроса по историческим продажам.',plan:'Изучить данные, построить модель, проверить на тестовом периоде.',experience:'Учебные проекты по прогнозированию спроса.',duration:'4 недели',price:'Без оплаты',contact:'team@example.test',prototype:'https://example.com/prototype'};
 await request('biz',{...proposal,clientId:crypto.randomUUID()},403);
 await request('team1',{...proposal,clientId:crypto.randomUUID(),prototype:'javascript:alert(1)'},400);
 const ids=[];
 for(const id of ['team1','team2','team3']){const clientId=crypto.randomUUID();ids.push(clientId);await request(id,{...proposal,clientId})}
 await request('team1',{...proposal,clientId:ids[0]});
 assert.equal((await request('team1')).proposals.length,1);passed++;
 await request('team1',{...proposal,clientId:crypto.randomUUID()});
 assert.equal((await request('team1')).proposals.length,2);passed++;
 assert.equal((await request('other')).proposals.length,0);passed++;
 assert.equal((await request(null)).proposals.length,0);passed++;
 await request('other',{action:'decide',task:draft.id,selected:[]},404);
 await request('biz',{action:'decide',task:draft.id,selected:['invalid']},400);
 await request('team1',{action:'reportProgress',proposal:ids[0],evidence:'Прототип готов: https://example.com'},403);
 await request('biz',{action:'decide',task:draft.id,selected:ids.slice(0,2)});
 const final=await request('biz');assert.equal(final.tasks.find(t=>t.id===draft.id).status,'closed');assert.equal(final.proposals.filter(p=>p.status==='selected').length,2);assert.equal(final.proposals.filter(p=>p.status==='rejected').length,2);passed+=3;
 await request('biz',{action:'saveTask',id:draft.id,...full,publish:true},409);
 await request('biz',{action:'decide',task:draft.id,selected:[]},409);
 await request('team1',{...proposal,clientId:crypto.randomUUID()},409);
 await request('team1',{action:'reportProgress',proposal:ids[0],evidence:'Построен проверяемый прототип: https://example.com'});
 assert.equal((await request('team1')).profile.points,0);passed++;
 await request('team1',{action:'confirmProgress',proposal:ids[0]},409);
 await request('other',{action:'confirmProgress',proposal:ids[0]},409);
 await request('biz',{action:'confirmProgress',proposal:ids[0]});
 await request('biz',{action:'confirmProgress',proposal:ids[0]},409);
 assert.equal((await request('team1')).profile.points,20);passed++;
 const none=await request('biz',{action:'saveTask',...full,publish:true});await request('team1',{...proposal,task:none.id,clientId:crypto.randomUUID()});await request('biz',{action:'decide',task:none.id,selected:[]});assert.equal((await request('team1')).proposals.find(p=>p.task===none.id).status,'rejected');passed++;
 const one=await request('biz',{action:'saveTask',...full,publish:true});const single=await request('team1',{...proposal,task:one.id,clientId:crypto.randomUUID()});await request('biz',{action:'decide',task:one.id,selected:[single.id]});assert.equal((await request('team1')).proposals.find(p=>p.task===one.id).status,'selected');passed++;
 const zero=await request('biz',{action:'saveTask',title:'Нужен сайт',category:'Разработка',problem:'Сделать сайт',confirmed:true,publish:true});await request('team3',{...proposal,task:zero.id,clientId:crypto.randomUUID()});
 const csrf=await mf.dispatchFetch('http://localhost/api/platform',{method:'POST',headers:{Origin:'https://evil.test'},body:'{}'});assert.equal(csrf.status,403);passed++;
 mkdirSync('.sites-runtime/test-modules',{recursive:true});
 for(const f of ['readiness','assistant']){let source=readFileSync('lib/'+f+'.ts','utf8').replace("from './readiness'","from './readiness.mjs'");writeFileSync('.sites-runtime/test-modules/'+f+'.mjs',ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ESNext,module:ts.ModuleKind.ESNext}}).outputText)}
 const {parseAssistant,clarify}=await import(pathToFileURL(resolve('.sites-runtime/test-modules/assistant.mjs')));
 const {emptyBrief,ready,level}=await import(pathToFileURL(resolve('.sites-runtime/test-modules/readiness.mjs')));
 assert.equal(ready(full).score,100);for(const [n,l] of [[0,'Требует уточнения'],[39,'Требует уточнения'],[40,'Рабочая'],[69,'Рабочая'],[70,'Готовая'],[89,'Готовая'],[90,'Приоритетная'],[100,'Приоритетная']]){assert.equal(level(n),l);passed++}
 const src={...emptyBrief,problem:'Нужен сайт'};const output=clarify(src.problem,src);assert.throws(()=>parseAssistant('not json',src));assert.throws(()=>parseAssistant(JSON.stringify({...output,questions:[]}),src));assert.throws(()=>parseAssistant(JSON.stringify({...output,draft:{...src,reward:'100000'}}),src));passed+=4;
 console.log(JSON.stringify({passed,result:'All workflow, ranking, AI validation, ownership, privacy, selection and progress checks passed.'}));
}finally{await mf.dispose()}

