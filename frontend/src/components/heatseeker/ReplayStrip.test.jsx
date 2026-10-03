/** @jest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import axios from 'axios';
import ReplayStrip from './ReplayStrip';

jest.mock('../../config/api', () => ({ API: '/api', BACKEND_URL: '', BACKEND_BASE: '' }));
jest.mock('axios', () => ({ get: jest.fn() }));

const SNAPS = [
  { id: 's1', asof: '2026-09-28T09:35:00Z' },
  { id: 's2', asof: '2026-09-28T10:10:00Z' },
  { id: 's3', asof: '2026-09-28T11:00:00Z' },
];

function replayPacket(id) {
  return {
    snapshot: { ticker: 'SPY', snapshot_id: id, asof: `asof-${id}`, exposure_basis: 'OI', formula_version: 'gex.v2' },
    strikes: [{ strike: 500 }], walls: [], grids: {},
  };
}

const dispId = (c) => c[0]?.asof;

beforeEach(() => {
  jest.useFakeTimers();
  axios.get.mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes('/solstice/manifest/')) return { data: { snapshots: SNAPS } };
    if (u.includes('recorder_health')) return { data: { durable: true } };
    const m = u.match(/\/solstice\/replay\/(.+)$/);
    if (m) return { data: replayPacket(decodeURIComponent(m[1])) };
    return { data: {} };
  });
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

async function loadStrip(onReplay = jest.fn()) {
  let utils;
  await act(async () => {
    utils = render(<ReplayStrip ticker="SPY" onReplay={onReplay} />);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId('solstice-replay-load'));
  });
  await waitFor(() => expect(screen.getByTestId('solstice-replay-count')).toBeInTheDocument());
  return { utils, onReplay };
}

test('selecting a dated session resets replay and uses the same date for manifest and comparison', async () => {
 const {onReplay}=await loadStrip();
 await act(async()=>fireEvent.click(screen.getByTestId('solstice-replay-play')));
 await waitFor(()=>expect(onReplay).toHaveBeenLastCalledWith(expect.objectContaining({snapshotId:'s1'})));
 fireEvent.change(screen.getByLabelText('Stored session date'),{target:{value:'2026-09-25'}});
 expect(onReplay).toHaveBeenLastCalledWith(null);
 expect(screen.queryByTestId('solstice-replay-scrub')).toBeNull();
 await act(async()=>fireEvent.click(screen.getByTestId('solstice-replay-load')));
 expect(axios.get).toHaveBeenCalledWith('/api/solstice/manifest/SPY?day=2026-09-25',expect.objectContaining({signal:expect.anything()}));
 await act(async()=>fireEvent.click(screen.getByTestId('solstice-compare-btn')));
 expect(axios.get).toHaveBeenCalledWith('/api/solstice/attribute/SPY?day=2026-09-25',expect.objectContaining({signal:expect.anything()}));
});

test('symbol changes and unmount abort a pending replay and discard late success', async()=>{
 const {utils,onReplay}=await loadStrip();
 let release;
 axios.get.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 fireEvent.click(screen.getByTestId('solstice-replay-play'));
 const pending=axios.get.mock.calls.at(-1)[1].signal;
 utils.rerender(<ReplayStrip ticker="QQQ" onReplay={onReplay}/>);
 expect(pending.aborted).toBe(true);
 await act(async()=>release({data:replayPacket('s1')}));
 expect(onReplay.mock.calls.filter(([display])=>display?.snapshotId==='s1')).toHaveLength(0);
 fireEvent.click(screen.getByTestId('solstice-replay-load'));
 const manifestSignal=axios.get.mock.calls.at(-1)[1].signal;
 utils.unmount();
 expect(manifestSignal.aborted).toBe(true);
});

test('absent gap metadata is unknown, never reported as zero',async()=>{
 const original=axios.get.getMockImplementation();
 axios.get.mockImplementation((url,opts)=>String(url).includes('/manifest/')?Promise.resolve({data:{day:'2026-09-28',snapshots:SNAPS}}):original(url,opts));
 await loadStrip();
 expect(screen.getByTestId('solstice-replay-strip')).toHaveTextContent('gap coverage unknown');
 expect(screen.getByTestId('solstice-replay-strip')).not.toHaveTextContent('0 declared gaps');
});

test('a replay response for a different owning record is refused visibly', async()=>{
 const {onReplay}=await loadStrip();
 axios.get.mockResolvedValue({data:replayPacket('wrong-record')});
 await act(async()=>fireEvent.click(screen.getByTestId('solstice-replay-play')));
 expect(onReplay).not.toHaveBeenCalled();
 expect(screen.getByRole('alert')).toHaveTextContent('RECORD_IDENTITY_MISMATCH');
 expect(screen.getByTestId('solstice-replay-play')).toHaveTextContent('Play');
});

test('Play advances recorded snapshots in order and stops at the last record', async () => {
  const { onReplay } = await loadStrip();
  await act(async () => {
    fireEvent.click(screen.getByTestId('solstice-replay-play'));
  });
  // First step lands on s1.
  await waitFor(() => {
    expect(onReplay.mock.calls.map(dispId)).toContain('asof-s1');
  });
  await act(async () => { jest.advanceTimersByTime(5000); });
  await act(async () => { jest.advanceTimersByTime(5000); });
  expect(onReplay.mock.calls.map(dispId).slice(0, 3)).toEqual(['asof-s1', 'asof-s2', 'asof-s3']);
  // Past the end: no further advance, play stops by itself.
  const n = onReplay.mock.calls.length;
  await act(async () => { jest.advanceTimersByTime(10000); });
  expect(onReplay.mock.calls.length).toBe(n);
  expect(screen.getByTestId('solstice-replay-play')).toHaveTextContent(/Play/);
});

test('scrubber jumps to a recorded timestamp and labels the range', async () => {
  const { onReplay } = await loadStrip();
  const scrub = await waitFor(() => screen.getByTestId('solstice-replay-scrub'));
  expect(scrub.getAttribute('max')).toBe('2');
  expect(screen.getByTestId('solstice-replay-range').textContent).toContain('09:35');
  await act(async () => {
    fireEvent.change(scrub, { target: { value: '2' } });
  });
  await waitFor(() => {
    expect(onReplay.mock.calls.map(dispId)).toContain('asof-s3');
  });
});

test('exiting replay stops playback and returns to live', async () => {
  const { onReplay } = await loadStrip();
  await act(async () => {
    fireEvent.click(screen.getByTestId('solstice-replay-play'));
  });
  await waitFor(() => {
    expect(onReplay.mock.calls.length).toBeGreaterThan(0);
  });
  await act(async () => {
    fireEvent.click(screen.getByTestId('solstice-replay-exit'));
  });
  expect(onReplay).toHaveBeenLastCalledWith(null);
  const n = onReplay.mock.calls.length;
  await act(async () => { jest.advanceTimersByTime(10000); });
  expect(onReplay.mock.calls.length).toBe(n);
});

test('slow recorded fetch never launches duplicate playback requests', async () => {
  let resolveFirst;
  const original = axios.get.getMockImplementation();
  axios.get.mockImplementation(url => String(url).endsWith('/replay/s1')
    ? new Promise(resolve => { resolveFirst = resolve; }) : original(url));
  const { onReplay } = await loadStrip();
  await act(async () => { fireEvent.click(screen.getByTestId('solstice-replay-play')); });
  await act(async () => { jest.advanceTimersByTime(10000); });
  const requests = () => axios.get.mock.calls.filter(([url]) => String(url).includes('/replay/'));
  expect(requests()).toHaveLength(1);
  await act(async () => { resolveFirst({ data: replayPacket('s1') }); });
  expect(onReplay).toHaveBeenLastCalledWith(expect.objectContaining({ asof: 'asof-s1' }));
  await act(async () => { jest.advanceTimersByTime(2000); });
  expect(requests()).toHaveLength(2);
  expect(String(requests()[1][0])).toContain('/replay/s2');
});
