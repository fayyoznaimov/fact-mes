// Reproducible browser smoke test using the Codex CUA tab API.
// Run only against _tools/react_sandbox.py (synthetic data on localhost:8791).
// Example in cua_repl:
// const {checkReport} = await import('file:///C:/.../frontend/browser-check.mjs');
// await checkReport(tab);
import assert from 'node:assert/strict';

export async function checkReport(tab) {
  const url = new URL(await tab.url());
  assert.equal(url.origin, 'http://127.0.0.1:8791', 'Only the synthetic sandbox is allowed');
  assert.equal(url.pathname, '/next/');
  const p = tab.playwright;
  await p.locator('#rep-table[aria-busy="false"]').waitFor({state:'visible'});
  await p.locator('#rep-reset').click();
  await p.locator('#rep-day').selectOption('2026.09.24');
  await p.locator('#rep-table[aria-busy="false"]').waitFor({state:'visible'});
  const looms = p.getByRole('textbox', {name:'Фильтр: Станок', exact:true});
  await looms.fill('J1-J14');
  assert.equal(await p.locator('#rep-table tbody tr').count(), 4);
  await tab.reload();
  await p.locator('#rep-table[aria-busy="false"]').waitFor({state:'visible'});
  assert.equal(await looms.getAttribute('value'), 'J1-J14');
  assert.equal(await p.locator('#rep-table tbody tr').count(), 4);
  await p.locator('#rep-reset').click();
  assert.equal(await p.locator('#rep-table tbody tr').count(), 8);
  await p.locator('#rep-table').getByText('D1',{exact:true}).click();
  await p.locator('#ls-dlg[open]').waitFor({state:'visible'});
  await p.locator('#ls-ppt').fill('3400');
  await p.locator('#ls-save').click();
  const doc = p.locator('#react-doc');
  await doc.getByRole('button',{name:'Вернуться к правке',exact:true}).click();
  assert.equal(await p.evaluate(()=>document.querySelector('#ls-ppt').value), '3400');
  await p.locator('#ls-dlg').getByRole('button',{name:'Отмена',exact:true}).click();
  await p.locator('#rp-from').fill('2026-09-24');
  await p.locator('#rp-to').fill('2026-09-24');
  await p.locator('#rp-go').click();
  await p.locator('#rp-approve').waitFor({state:'visible'});
  const period = p.locator('#react-period');
  assert.match(await period.innerText(), /24\.09\.2026 – 24\.09\.2026/);
  assert.equal(await period.locator('tbody tr').count(), 9); // eight looms and the original totals row
  await p.locator('#rp-approve').click();
  await doc.locator('.ack:not(.hidden)').waitFor({state:'visible'});
  assert.equal(await doc.getByRole('button',{name:'Провести',exact:true}).isEnabled(), false);
  await doc.getByRole('checkbox').check();
  assert.equal(await doc.getByRole('button',{name:'Провести',exact:true}).isEnabled(), true);
  await doc.getByRole('button',{name:'Вернуться к правке',exact:true}).click();
  await p.locator('#rep-day').selectOption('2026.09.24');
  await p.locator('#rep-table[aria-busy="false"]').waitFor({state:'visible'});
  const download = p.waitForEvent('download');
  await p.locator('#rep-excel').click();
  const file = await (await download).path();
  assert.ok(file?.endsWith('.xlsx'));
  const errors = await tab.dev.logs({levels:['error'],limit:10});
  assert.equal(errors.length, 0);
  return {passed:true,scenarios:['filters persist','setup cancellation preserves input',
    'period dates and rows','warning acknowledgement','Excel download','no console errors']};
}
