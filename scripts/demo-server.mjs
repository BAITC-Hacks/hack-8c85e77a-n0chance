import {Miniflare} from 'miniflare';
import {createServer} from 'node:http';
import {readFileSync,readdirSync,existsSync,statSync} from 'node:fs';
import {resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {demoData} from './demo-data.mjs';
process.chdir(resolve(dirname(fileURLToPath(import.meta.url)),'..'));
const port=Number(process.env.PORT||5173);
if(!existsSync('dist/server/index.js'))throw Error('Сначала выполните npm run build.');
const root=resolve('dist/server'),files=readdirSync(root,{recursive:true}).filter(p=>p.endsWith('.js')&&p!=='index.js');
const mf=new Miniflare({modules:['index.js',...files].map(path=>({type:'ESModule',path:resolve(root,path),contents:readFileSync(resolve(root,path),'utf8')})),modulesRoot:root,compatibilityDate:'2026-05-15',compatibilityFlags:['nodejs_compat'],d1Databases:{DB:'most-local-demo'},d1Persist:resolve('.demo-data'),bindings:{APP_DEMO:'true'},cf:false});
const db=await mf.getD1Database('DB');
await db.prepare('CREATE TABLE IF NOT EXISTS __local_migrations(name TEXT PRIMARY KEY)').run();
for(const file of readdirSync('drizzle').filter(f=>f.endsWith('.sql')).sort()){
 if(await db.prepare('SELECT name FROM __local_migrations WHERE name=?').bind(file).first())continue;
 const statements=readFileSync('drizzle/'+file,'utf8').split('--> statement-breakpoint').map(s=>s.trim()).filter(Boolean);
 await db.batch([...statements.map(sql=>db.prepare(sql)),db.prepare('INSERT INTO __local_migrations(name) VALUES(?)').bind(file)]);
}
if(!await db.prepare("SELECT name FROM __local_migrations WHERE name='demo-seed-v1'").first()){
 const statements=[];
 for(const p of demoData.profiles)statements.push(db.prepare('INSERT OR IGNORE INTO profiles(id,role,name,university,skills,interests,technologies) VALUES(?,?,?,?,?,?,?)').bind(p.id,p.role,p.name,p.university,p.skills,p.interests,p.technologies));
 for(const [i,t] of [...demoData.cards,...demoData.drafts].entries()){
  const row={...t,owner:'demo-business',status:i<5?'published':'draft',created:new Date(Date.now()-i*60000).toISOString()},keys=Object.keys(row);
  statements.push(db.prepare('INSERT OR IGNORE INTO tasks('+keys.join(',')+') VALUES('+keys.map(()=>'?').join(',')+')').bind(...keys.map(k=>row[k])));
 }
 for(const p of demoData.proposals){const row={...p,created:new Date().toISOString()},keys=Object.keys(row);statements.push(db.prepare('INSERT OR IGNORE INTO proposals('+keys.join(',')+') VALUES('+keys.map(()=>'?').join(',')+')').bind(...keys.map(k=>row[k])))}
 statements.push(db.prepare("INSERT INTO __local_migrations(name) VALUES('demo-seed-v1')"));await db.batch(statements);
}
const personas=new Map(demoData.profiles.map(p=>[p.id,p]));
const mime={'.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.json':'application/json','.ico':'image/x-icon'};
const assetRoot=resolve('dist/client');
const server=createServer(async(req,res)=>{try{
 const host=req.headers.host,allowed=['localhost:'+port,'127.0.0.1:'+port];if(!allowed.includes(host)){res.writeHead(403);return res.end('Invalid host')}
 const origin='http://'+host,url=new URL(req.url,origin);
 if(url.pathname==='/api/demo-switch'){if(req.method!=='POST'||req.headers.origin!==origin){res.writeHead(403);return res.end()}let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>2048){res.writeHead(413);return res.end()}}
 let body;try{body=JSON.parse(raw)}catch{res.writeHead(400);return res.end()}if(!personas.has(body.id)){res.writeHead(400);return res.end()}
 res.writeHead(200,{'Content-Type':'application/json','Set-Cookie':'most_demo='+body.id+'; Path=/; HttpOnly; SameSite=Strict'});return res.end('{"ok":true}')}
 const file=resolve(assetRoot,'.'+decodeURIComponent(url.pathname));if(file.startsWith(assetRoot+'/')||file.startsWith(assetRoot+'\\')){if(existsSync(file)&&statSync(file).isFile()){res.writeHead(200,{'Content-Type':mime[extname(file)]||'application/octet-stream'});return res.end(readFileSync(file))}}
 const cookies=(req.headers.cookie||'').split(';').map(s=>s.trim());const chosen=cookies.find(s=>s.startsWith('most_demo='))?.slice(10);const person=personas.get(chosen)||personas.get('demo-business');
 const headers=new Headers();for(const [k,v] of Object.entries(req.headers))if(v&&!k.startsWith('oai-authenticated-user-')&&!['host','connection','content-length','accept-encoding'].includes(k))headers.set(k,Array.isArray(v)?v.join(','):v);
 headers.set('oai-authenticated-user-id',person.id);headers.set('oai-authenticated-user-email',person.id+'@example.test');
 let body; if(!['GET','HEAD'].includes(req.method)){const chunks=[];let size=0;for await(const c of req){size+=c.length;if(size>100000){res.writeHead(413);return res.end()}chunks.push(c)}body=Buffer.concat(chunks)}
 const response=await mf.dispatchFetch(url.toString(),{method:req.method,headers,body});res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
 }catch(error){console.error(error);res.writeHead(500,{'Content-Type':'text/plain; charset=utf-8'});res.end('Не удалось обработать запрос.') }});
server.listen(port,'127.0.0.1',()=>console.log('МОСТ · локальная демонстрация: http://localhost:'+port+'\nДанные сохраняются в .demo-data. Ctrl+C — остановить.'));
async function stop(){server.close();await mf.dispose();process.exit(0)}
process.on('SIGINT',stop);process.on('SIGTERM',stop);
