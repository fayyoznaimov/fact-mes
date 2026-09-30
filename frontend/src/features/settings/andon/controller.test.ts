import { describe, expect, it, vi } from 'vitest';
import { AndonController } from './controller';

function setup() {
  const io = {
    postSettings: vi.fn<() => Promise<unknown>>().mockResolvedValue({ok: true}),
    changed: vi.fn(), say: vi.fn(),
  };
  const controller = new AndonController(io);
  return {controller, io};
}

describe('setValues', () => {
  it('seeds the form fields', () => {
    const {controller: c} = setup();
    c.setValues({warn: '10', alarm: '20', notify: '30'});
    expect(c.state).toEqual({warn: '10', alarm: '20', notify: '30'});
  });
});

describe('save', () => {
  it('clamps and posts the thresholds', async () => {
    const {controller: c, io} = setup();
    c.setWarn('-1'); c.setAlarm('abc'); c.setNotify('15.9');
    await c.save();
    expect(io.postSettings).toHaveBeenCalledWith({warn: '0', alarm: '0', notify: '15'});
    expect(c.state).toEqual({warn: '0', alarm: '0', notify: '15'});
    expect(io.say).toHaveBeenCalledWith('Пороги андона сохранены — доски в цехе уже работают по ним');
  });
  it('reports a failure', async () => {
    const {controller: c, io} = setup();
    io.postSettings.mockRejectedValueOnce(new Error('нет прав'));
    await c.save();
    expect(io.say).toHaveBeenCalledWith('Не сохранилось: нет прав', true);
  });
});
