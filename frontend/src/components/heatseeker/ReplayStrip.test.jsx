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
