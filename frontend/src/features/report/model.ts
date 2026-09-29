export type Scalar = number | string | null | undefined;
export type Row = { loom: string; setup?: Record<string, Scalar> | null;
  [key: string]: Scalar | Record<string, Scalar> | boolean };
export type Column = { k: string; t: string; g?: string; text?: 'loom' | 'sub';
  p?: (v: Scalar) => string; d?: number; f?: 'sum' | 'avg'; s?: string; sep?: boolean; ph?: boolean };
export type View = { filters: Record<string, string>; sort: {i: number; dir: number} | null; hidden: string[]; flag: string };
export type Snapshot = View & {rows: Row[]; day: string; setupEdit: boolean; exportAllowed: boolean; loading?: boolean; exportBusy?: boolean};
export const value = (row: Row, key: string): Scalar => {
  const v = row[key]; return typeof v === 'number' || typeof v === 'string' ? v : null;
};
export const nf = (v: Scalar, digits = 0) => v == null || v === '' ? '' : Number(v).toLocaleString(
  document.documentElement.lang === 'en' ? 'en-GB' : 'ru-RU', { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const paint = (v: Scalar, low: number, high: number, red: number) => {
  const n = Number(v);
  if (v == null || v === '' || isNaN(n) || n === 0) return '';
  return n >= red ? ' c-red' : n >= low && n <= high ? ' c-yel' : '';
};
export const paintEff = (v: Scalar) => {
  const n = Number(v);
  if (v == null || v === '' || isNaN(n)) return '';
  return n >= 1 && n <= 69 ? ' c-red' : n >= 70 && n <= 79 ? ' c-yel' : '';
};
export const paintRpm = () => '';
const grp4 = (pre: string, name: string, pa: (v: Scalar) => string, pt: (v: Scalar) => string,
  dt = 0, f: 'sum' | 'avg' = 'sum'): Column[] => ['a','b','c','total'].map((s, i) => ({
    k: `${pre}_${s}`, t: s === 'total' ? 'Итог' : s.toUpperCase(), g: name,
    p: s === 'total' ? pt : pa, d: s === 'total' ? dt : 0, sep: i === 0, f }));
const grp3 = (pre: string, label: string): Column[] => ['a','b','c'].map((s, i) => ({
  k: `mend_${pre}_${s}`, t: `${label} ${s.toUpperCase()}`, g: 'Mending time, сек', sep: i === 0, f: 'avg' }));
export const COLUMNS: Column[] = [
  {k:'sr',t:'Sr#'}, {k:'size_cm',t:'Размер'}, {k:'rpm',t:'Об/мин',p:paintRpm,f:'avg'},
  {k:'prod100_kg',t:'100% кг',d:1,f:'sum'},
  {k:'norm_pct',t:'Норма 1С, %',d:0,f:'avg',p:v => v != null && Number(v) < 90 ? ' bad' : ''},
  {k:'loom',t:'Станок',text:'loom'}, {k:'design',t:'Дизайн',text:'sub'},
  {k:'ppt',t:'PPT',g:'Заправка',sep:true}, {k:'weight_kg',t:'Вес шт, кг',g:'Заправка',d:3,s:'weight_kg'},
  {k:'panels',t:'Панели',g:'Заправка',s:'panels'}, {k:'gsm',t:'GSM',g:'Заправка',s:'gsm'},
  {k:'y_pile',t:'Ворс · лот',g:'Заправка',text:'sub',s:'pile'},
  {k:'y_ground',t:'Грунт · лот',g:'Заправка',text:'sub',s:'ground'},
  {k:'y_weft',t:'Уток · лот',g:'Заправка',text:'sub',s:'weft'},
  {k:'y_hem',t:'Кромка · лот',g:'Заправка',text:'sub',s:'hem'},
  {k:'y_fancy',t:'Бордюр · лот',g:'Заправка',text:'sub',s:'fancy'},
  ...grp4('eff','Efficiency',paintEff,paintEff,1,'avg'),
  ...grp4('pile','Ворс (Pile)',v=>paint(v,30,40,41),v=>paint(v,91,120,121)),
  ...grp4('weft','Уток (Weft)',v=>paint(v,50,60,61),v=>paint(v,91,120,121)),
  ...grp4('ground','Основа (Ground)',v=>paint(v,50,60,61),v=>paint(v,45,60,61)),
  ...grp4('other','Прочие',v=>paint(v,16,20,21),v=>paint(v,91,120,121)),
  ...grp3('vors','Vors'), ...grp3('utog','Utog'), ...grp3('karenoy','Karenoy'),
];
export const SHIFT_GROUPS = ['Efficiency','Ворс (Pile)','Уток (Weft)','Основа (Ground)','Прочие'];
export const G_SETUP = 'Заправка', G_MEND = 'Mending time, сек';
export function visibleColumns(hidden: string[]) {
  const out: {c: Column; i: number}[] = []; let previous = '';
  COLUMNS.forEach((c,i) => {
    const group = c.g || '', first = !!group && group !== previous; previous = group;
    if (!group || !hidden.includes(group)) out.push({c:{...c,sep:!!c.sep || first},i});
    else if (SHIFT_GROUPS.includes(group)) { if(c.k.endsWith('_total')) out.push({c:{...c,sep:true},i}); }
    else if(first) out.push({c:{k:'',t:'…',g:group,sep:true,ph:true},i:-1});
  });
  return out;
}
export function numTest(expr: string): ((v: Scalar) => boolean) | null {
  const s = expr.replace(/\s/g,'').replace(/,/g,'.');
  let m = s.match(/^(>=|<=|>|<|=)?(-?\d+(?:\.\d+)?)$/);
  if (m) { const op=m[1] || '=', x=+m[2]; return v => v != null && v !== '' && !isNaN(Number(v)) &&
    !!({'>':Number(v)>x,'<':Number(v)<x,'>=':Number(v)>=x,'<=':Number(v)<=x,'=':Number(v)===x})[op]; }
  m=s.match(/^(-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)$/);
  if(m) { const a=Math.min(+m[1],+m[2]),b=Math.max(+m[1],+m[2]);
    return v=>v!=null && v!=='' && !isNaN(Number(v)) && Number(v)>=a && Number(v)<=b; }
  return null;
}
export const subTest = (expr: string) => (v: Scalar) => String(v ?? '').toLowerCase().includes(expr.trim().toLowerCase());
export function textTest(expr: string) {
  const items=expr.toUpperCase().split(/[,\s]+/).filter(Boolean);
  const parts=(s: string)=>s.match(/^([A-Z]+)(\d+)$/) || [];
  return (v: Scalar) => { const name=String(v || '').toUpperCase(); return items.some(it=>{
    const [from,to]=it.split('-');
    if(to) {const a=parts(from),b=parts(to),c=parts(name); return !!a[1] && c[1]===a[1] && +c[2]>=+a[2] && +c[2]<=+b[2];}
    return /^[A-Z]+$/.test(it) ? name.startsWith(it) && /^\d+$/.test(name.slice(it.length)) : name===it;
  }); };
}
export function selectRows(all: Row[], view: View) {
  const tests: {key:string; test:(v:Scalar)=>boolean}[]=[], bad:number[]=[];
  COLUMNS.forEach((c,i)=>{
    const expr=(view.filters[i] || '').trim(); if(!expr)return;
    const test=c.text==='sub'?subTest(expr):c.text?textTest(expr):numTest(expr);
    if(test)tests.push({key:c.k,test});else bad.push(i);
  });
  const rows=all.filter(r=>tests.every(t=>t.test(value(r,t.key))) &&
    (view.flag==='all' || (view.flag==='red' ? r._red : r._red || r._yel)));
  if(view.sort) {
    const c=COLUMNS[view.sort.i],dir=view.sort.dir;
    if(c)rows.sort((a,b)=>{
      const x=value(a,c.k),y=value(b,c.k),empty=(v:Scalar)=>v==null || v==='' || (!c.text && isNaN(Number(v)));
      if(empty(x)||empty(y))return Number(empty(x))-Number(empty(y));
      return (c.text?String(x).localeCompare(String(y),'ru',{numeric:true}):Number(x)-Number(y))*dir;
    });
  }
  return {rows,bad};
}
export function nextSort(sort: View['sort'], i: number): View['sort'] {
  const first=COLUMNS[i].text?1:-1;
  return !sort || sort.i!==i ? {i,dir:first} : sort.dir===first ? {i,dir:-first} : null;
}
// Ровно прежние операции суммирования/усреднения: миграция не меняет формулы.
export const sum=(rows:Row[],key:string)=>rows.reduce((a,r)=>a+(Number(value(r,key))||0),0);
export function average(rows:Row[],key:string) {
  const values=rows.map(r=>value(r,key)).filter(v=>v!=null && v!=='');
  return values.length?values.reduce<number>((a,v)=>a+Number(v),0)/values.length:null;
}
