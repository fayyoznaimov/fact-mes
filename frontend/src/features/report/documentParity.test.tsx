import { runInNewContext } from 'node:vm';
import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { source } from '../../test/legacy';
import { DocumentBody, type CheckedDocument } from './DocumentBody';

const cut=(a:string,b:string)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
const base={looms:1,days:2,shifts:6,effic:75.14,picks:100000,rows:30,towels:60,towels_known:false,kg:38.1,pile:5,weft:4,ground:3,other:2};
const fixtures:CheckedDocument[]=[
  {type:'report',title:'Отчёт',type_title:'Производственный отчёт',checksum:'a',errors:[],warnings:['Неполно'],summary:base,changes:[],
    result:{rows:[{...base,loom:'D1',designs:['D327','<тест>'],gsm:[420]}],totals:base}},
  {type:'setup',title:'Заправка',type_title:'Заправка',checksum:'b',errors:[],warnings:[],summary:{...base,changed_looms:1,changed_fields:3},result:{},changes:[
    {loom:'D1',field:'ppt',label:'PPT',before:3200,after:3300,before_source:'1С',after_source:'вручную',delta:100,since:'2026.09.24',since_by:'Мастер',context:{Ткань:'TEST'}},
    {loom:'D1',field:'weight',label:'Вес',before:null,after:.635,after_source:'вручную'},
    {loom:'D1',field:'lot',label:'Лот',before:'<LOT>',after:''},
  ]},
];
const nodes=(root:Element)=>{
  // HTML templates indent table cells; these text nodes have no rendered content.
  root.querySelectorAll('table,thead,tbody,tr').forEach(e=>Array.from(e.childNodes).forEach(n=>{
    if(n.nodeType===Node.TEXT_NODE&&!n.textContent?.trim())n.remove();
  }));
  return Array.from(root.querySelectorAll('*')).map(e=>({tag:e.tagName,classes:e.className,text:(e.textContent||'').replace(/\s+/g,' ').trim()}));
};
function legacy(c:CheckedDocument){
  const doc=document.implementation.createHTMLDocument();doc.documentElement.lang=document.documentElement.lang;
  const script=[source.match(/^const nf = .*$/m)![0],source.match(/^const esc = .*$/m)![0],
    cut('function archiveTable(', 'const auditNames='),
    cut('const docDialog=', 'function docConfirm('),
    cut('const dxDay=', 'function dxMoneyDiff('),
    'docRender(c);',
  ].join('\n');
  runInNewContext(script,{document:doc,$:(s:string)=>doc.querySelector(s),tr:(s:string)=>s,c},{timeout:1000});
  return doc.querySelector('#doc-body')!;
}
afterEach(()=>{cleanup();document.documentElement.lang='ru';});
it.each(['ru','en'])('preserves period and setup document text, tables, classes and warnings (%s)',lang=>{
  document.documentElement.lang=lang;
  for(const fixture of fixtures){
    for(const patch of [{},{errors:['Ошибка < & >']},{may_post:false},{warnings:['Проверьте'],errors:[]}]){
      const checked={...fixture,...patch};const {container}=render(<DocumentBody checked={checked}/>);
      expect(nodes(container)).toEqual(nodes(legacy(checked)));cleanup();
    }
  }
});
