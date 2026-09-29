import { describe, expect, it, vi, afterEach } from 'vitest';
import { ReportController, prepareRows, requestReport } from './controller';
import { COLUMNS, type Snapshot } from './model';

const initial:Snapshot={rows:[{loom:'D1',rpm:480}],day:'2026.09.24',filters:{},sort:null,hidden:[],flag:'all',setupEdit:true,exportAllowed:true};
const deferred=()=>{let resolve!:(v:unknown)=>void,reject!:(v:unknown)=>void;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function setup(){
  const io={request:vi.fn<(day:string,signal:AbortSignal)=>Promise<unknown>>(),changed:vi.fn(),publish:vi.fn(),error:vi.fn(),storage:localStorage};
  const controller=new ReportController(initial,['2026.09.26','2026.09.25','2026.09.24'],io);
  return {controller,io};
}
afterEach(()=>{localStorage.clear();vi.unstubAllGlobals();});
describe('Report requests',()=>{
  it('cancels older requests and ignores their late successful response',async()=>{
    const {controller:c,io}=setup(),a=deferred(),b=deferred();
    io.request.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
    const first=c.load(false,'2026.09.25'),second=c.load(false,'2026.09.26');
    expect(io.request.mock.calls[0][1].aborted).toBe(true);
    b.resolve({rows:[{loom:'J14'}]});await second;
    a.resolve({rows:[{loom:'D2'}]});await first;
    expect(c.state.day).toBe('2026.09.26');expect(c.state.rows[0].loom).toBe('J14');
    expect(io.publish).toHaveBeenCalledOnce();expect(io.error).not.toHaveBeenCalled();
  });
  it('restores the displayed day after overlapping requests fail and allows retry',async()=>{
    const {controller:c,io}=setup(),a=deferred(),b=deferred();
    io.request.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
    const first=c.load(false,'2026.09.25'),second=c.load(false,'2026.09.26');
    b.reject(new Error('нет сети'));await second;a.reject(new Error('old error'));await first;
    expect(c.state.day).toBe('2026.09.24');expect(c.state.rows).toEqual(initial.rows);
    expect(io.error).toHaveBeenCalledExactlyOnceWith('Отчёт не загрузился: нет сети');
    io.request.mockResolvedValueOnce({rows:[{loom:'D3'}]});await c.load(false,'2026.09.26');
    expect(c.state.rows[0].loom).toBe('D3');
  });
  it('automatically skips incomplete days but respects explicit day selection',async()=>{
    const {controller:c,io}=setup();io.request
      .mockResolvedValueOnce({rows:[{loom:'D1',eff_c:null}]})
      .mockResolvedValueOnce({rows:[{loom:'D1',eff_c:0},{loom:'D2',eff_c:null}]});
    await c.load(true,'2026.09.26');expect(c.state.day).toBe('2026.09.25');
    expect(io.request.mock.calls.map(x=>x[0])).toEqual(['2026.09.26','2026.09.25']);
    io.request.mockResolvedValueOnce({rows:[{loom:'D1',eff_c:null}]});
    await c.load(false,'2026.09.26');expect(c.state.day).toBe('2026.09.26');
  });
  it('does not skip an empty day or request anything with no available date',async()=>{
    const {controller:c,io}=setup();io.request.mockResolvedValueOnce({rows:[]});
    await c.load(true,'2026.09.26');expect(io.request).toHaveBeenCalledOnce();
    c.setDays([]);await c.load();expect(io.request).toHaveBeenCalledOnce();
  });
  it('disposal and replacement of available days prevent stale publication',async()=>{
    for(const finish of ['dispose','days']){
      const {controller:c,io}=setup(),a=deferred();io.request.mockReturnValueOnce(a.promise);
      const request=c.load();if(finish==='dispose')c.dispose();else c.setDays(['2026.09.26']);
      const count=io.publish.mock.calls.length;a.resolve({rows:[{loom:'OLD'}]});await request;
      expect(io.publish.mock.calls.length).toBe(count);expect(io.request.mock.calls[0][1].aborted).toBe(true);
    }
  });
  it('rejects malformed responses without replacing the last valid report',async()=>{
    const {controller:c,io}=setup();io.request.mockResolvedValueOnce({rows:[{rpm:100}]});
    await c.load();expect(c.state.rows).toEqual(initial.rows);expect(io.error).toHaveBeenCalled();
  });
});
describe('Saved view and row preparation',()=>{
  it('persists the legacy format and restores filters, sorting and collapsed groups',()=>{
    const {controller:c}=setup();const view={filters:{5:'J1-J14'},sort:{i:2,dir:-1},hidden:['Заправка'],flag:'warn'};
    c.setView(view);expect(JSON.parse(localStorage.getItem('rep-view')!).sig).toBe(COLUMNS.map(c=>c.k).join(','));
    const next=setup().controller;expect(next.state).toMatchObject(view);
  });
  it('ignores stale column signatures and invalid persisted sorting',()=>{
    localStorage.setItem('rep-view',JSON.stringify({sig:'old',f:{5:'D'},sort:{i:999,dir:1}}));
    expect(setup().controller.state.filters).toEqual({});
    localStorage.setItem('rep-view',JSON.stringify({sig:COLUMNS.map(c=>c.k).join(','),f:{999:'D',5:'J'},sort:{i:999,dir:1}}));
    expect(setup().controller.state).toMatchObject({filters:{5:'J'},sort:null});
  });
  it('prepares yarn slots and flags without mutating API rows or turning null into zero',()=>{
    const raw={loom:'D1',eff_a:69,rpm:400,achieved_kg:null,yarns:JSON.stringify([{slot:'pile',yarn:'20/2',lot:'123'},{slot:'weft2',yarn:'16/1'},{slot:'hemply',lot:'456'}])};
    const [row]=prepareRows({rows:[raw]});expect(row).toMatchObject({_red:true,_yel:false,achieved_kg:null,y_pile:'20/2 · 123',y_hem:'16/1 + ? · 456'});
    expect(raw).not.toHaveProperty('_red');
    expect(prepareRows({rows:[{loom:'J1',yarns:'broken',rpm:400}]} )[0]).toMatchObject({_red:false,y_pile:''});
  });
});
describe('HTTP errors and authentication',()=>{
  it('uses same-origin cookies and forwards cancellation',async()=>{
    const fetch=vi.fn().mockResolvedValue(new Response('{"rows":[]}',{headers:{'Content-Type':'application/json'}}));vi.stubGlobal('fetch',fetch);
    const signal=new AbortController().signal;expect(await requestReport('2026.09.25',signal,vi.fn())).toEqual({rows:[]});
    expect(fetch).toHaveBeenCalledWith('/api/report?day=2026.09.25',{signal,credentials:'same-origin'});
  });
  it.each([401,403,500])('handles HTTP %s without publishing rows',async status=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{"error":"отказ"}',{status,headers:{'Content-Type':'application/json'}})));
    const expire=vi.fn();await expect(requestReport('2026.09.25',new AbortController().signal,expire)).rejects.toThrow(status===401?'сессия закончилась':'отказ');
    expect(expire).toHaveBeenCalledTimes(status===401?1:0);
  });
  it('reports a non-JSON proxy response and a network failure clearly',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>bad</html>',{status:502})));
    await expect(requestReport('day',new AbortController().signal,vi.fn())).rejects.toThrow('ошибкой 502');
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('fetch failed')));
    await expect(requestReport('day',new AbortController().signal,vi.fn())).rejects.toThrow('нет связи');
  });
});
