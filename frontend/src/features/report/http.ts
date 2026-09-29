export class ApiError extends Error {
  constructor(message:string,public status:number,public data:unknown){super(message);}
}
export async function requestJson<T>(path:string,expire:()=>void,body?:unknown,signal?:AbortSignal):Promise<T>{
  let response:Response;
  try { response=await fetch(path,{credentials:'same-origin',signal,...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}); }
  catch(error){if(signal?.aborted)throw error;throw new Error('нет связи с сервером цеха');}
  if(signal?.aborted)throw new DOMException('Aborted','AbortError');
  if(response.status===401){expire();throw new ApiError('сессия закончилась — войдите снова',401,null);}
  if(!(response.headers.get('Content-Type')||'').includes('json'))throw new ApiError(response.ok?'сервер ответил не данными':`сервер ответил ошибкой ${response.status}`,response.status,null);
  const data=await response.json();
  if(data?.error||!response.ok)throw new ApiError(data?.error||`сервер ответил ошибкой ${response.status}`,response.status,data);
  return data;
}
