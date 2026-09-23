export const categories=['Разработка','Аналитика','Дизайн','Маркетинг','Исследования'];
export type Brief={title:string;category:string;problem:string;need:string;users:string;result:string;metric:string;resources:string;constraints:string;contact:string;interaction:string;deadline:string;reward:string};
export const emptyBrief:Brief={title:'',category:'Разработка',problem:'',need:'',users:'',result:'',metric:'',resources:'',constraints:'',contact:'',interaction:'',deadline:'',reward:''};
export const criteria=[
{key:'problem',label:'Контекст и потребность',weight:20,min:30,hint:'Что происходит сейчас и что нужно изменить? Заполните контекст (30 символов) и потребность (10 символов).'},
{key:'resources',label:'Данные и материалы',weight:20,min:20,hint:'Какие данные, примеры или источники вы предоставите? Не менее 20 символов.'},
{key:'result',label:'Ожидаемый результат',weight:15,min:20,hint:'Что команда должна передать: прототип, исследование или сервис? Не менее 20 символов.'},
{key:'metric',label:'Критерии успеха',weight:15,min:15,hint:'По какому измеримому показателю вы примете работу? Не менее 15 символов.'},
{key:'constraints',label:'Ограничения',weight:10,min:15,hint:'Какие сроки, технологии, доступы или иные границы нужно учитывать? Не менее 15 символов.'},
{key:'users',label:'Пользователи',weight:10,min:10,hint:'Кто будет пользоваться результатом? Не менее 10 символов.'},
{key:'contact',label:'Связь с бизнесом',weight:10,min:5,hint:'Укажите контакт (5 символов) и формат консультаций / обратной связи (10 символов).'}
] as const;
export function ready(b:Partial<Brief>){const checks=criteria.map(c=>({...c,done:String(b[c.key]??'').trim().length>=c.min&&(c.key!=='problem'||String(b.need??'').trim().length>=10)&&(c.key!=='contact'||String(b.interaction??'').trim().length>=10)}));return {checks,score:checks.reduce((n,c)=>n+(c.done?c.weight:0),0)}}
export function validDate(d:string){return !d||/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d))&&new Date(d).toISOString().slice(0,10)===d}
export function canPublish(b:Brief){return b.title.trim().length>=3&&b.problem.trim().length>=3&&validDate(b.deadline)}
export function level(score:number){return score<40?'Требует уточнения':score<70?'Рабочая':score<90?'Готовая':'Приоритетная'}
export function taskScore(t:Partial<Brief>&{confirmed?:number;example?:boolean}){return t.confirmed||t.example?ready(t).score:0}

