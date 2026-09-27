/** @jest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import VolumeProfileGrid from './VolumeProfileGrid';

function mockData(withVolume = true) {
  return {
    spot: 650,
    nodes: {
      regime: 'positive',
      king: { strike: 650, gex: 100 },
      gamma_flip: 640,
      floors: [{ strike: 648 }],
      ceilings: [{ strike: 655 }],
      gatekeepers: [{ strike: 645 }, { strike: 660 }],
      max_pain: 645,
      air_pockets: [{ low: 630, high: 635 }],
    },
    strikes: [652, 650, 648].map((s) => ({
      strike: s,
      gex: (s - 650) * 100,
      total_oi: 100,
      ...(withVolume ? { total_volume: (660 - s) * 10 } : {}),
    })),
  };
}

test('renders node strip with regime, king, air pockets', () => {
  render(<VolumeProfileGrid data={mockData()} spot={650} />);
  const strip = screen.getByTestId('volume-profile-nodes');
  expect(strip.textContent).toContain('Regime');
  expect(strip.textContent).toContain('positive');
  expect(strip.textContent).toContain('King');
  expect(strip.textContent).toContain('Air');
  expect(strip.textContent).toContain('630');
});

test('renders volume column when strike volume exists', () => {
  const { container } = render(<VolumeProfileGrid data={mockData(true)} spot={650} />);
  expect(container.querySelectorAll('.volume-profile-vol-cell').length).toBe(3);
});

test('hides volume column without strike volume', () => {
  const { container } = render(<VolumeProfileGrid data={mockData(false)} spot={650} />);
  expect(container.querySelectorAll('.volume-profile-vol-cell').length).toBe(0);
  // Nodes still render — volume absence must not blank the levels.
  expect(screen.getByTestId('volume-profile-nodes')).toBeInTheDocument();
});

test('empty state without data', () => {
  render(<VolumeProfileGrid data={null} spot={null} />);
  expect(screen.getByTestId('volume-profile-grid').textContent).toContain('No profile data');
});

function profileRow(container, strike) {
  return [...container.querySelectorAll('tbody tr')].find(row => row.querySelector('.volume-profile-strike').textContent === `${strike}.0`);
}

const mixedCoverage = {
  grid: {
    expiries: ['2026-10-02', '2026-10-09'], strikes: [103, 102, 101, 100, 99],
    grid: {
      '2026-10-02': { 103: 1000, 102: 0, 101: null, 99: 1 },
      '2026-10-09': { 103: 1000, 102: 0, 101: 0, 100: 0, 99: null },
    },
  },
};

test('missing and partial expiry readings never become zero or AIR, while measured zero remains AIR', () => {
  const { container } = render(<VolumeProfileGrid data={mixedCoverage} spot={103} />);
  for (const strike of [101, 100, 99]) {
    const row = profileRow(container, strike);
    expect(row.querySelector('.volume-profile-strike')).not.toHaveClass('is-air');
    expect(row.textContent).not.toContain('AIR');
    expect([...row.querySelectorAll('.volume-profile-cell')].some(c => c.textContent === '—')).toBe(true);
  }
  const zero = profileRow(container, 102);
  expect(zero.textContent).toContain('AIR');
  expect([...zero.querySelectorAll('.volume-profile-cell')].map(c => c.textContent)).toEqual(['0', '0']);
  expect(container.querySelector('.volume-profile-air-hint').textContent).toBe('Air: 1 strikes');
});

test('flat missing selected GEX stays unavailable; explicit zero and legacy total GEX stay readable', () => {
  const data = { strikes: [{ strike: 105, gex: 1000 }, { strike: 104, gex: 0 }, { strike: 103, gex: null }, { strike: 102 }, { strike: 101, total_gex: 0 }, { strike: 100, gex: null, total_gex: 5 }] };
  const { container } = render(<VolumeProfileGrid data={data} spot={105} />);
  for (const strike of [103, 102, 100]) {
    const row = profileRow(container, strike);
    expect(row.querySelector('.volume-profile-cell').textContent).toBe('—');
    expect(row.textContent).not.toContain('AIR');
  }
  expect(profileRow(container, 104).textContent).toContain('AIR');
  expect(profileRow(container, 101).querySelector('.volume-profile-cell').textContent).toBe('0');
});

test.each([NaN, Infinity, -Infinity, '0'])('invalid reading %s is unavailable and never AIR', value => {
  const data = { grid: { expiries: ['2026-10-02'], strikes: [101, 100], grid: { '2026-10-02': { 101: 1000, 100: value } } } };
  const { container } = render(<VolumeProfileGrid data={data} spot={101} />);
  const row = profileRow(container, 100);
  expect(row.querySelector('.volume-profile-cell').textContent).toBe('—');
  expect(row.textContent).not.toContain('AIR');
});

test('missing expiry list cannot manufacture a zero summed reading', () => {
  const { container } = render(<VolumeProfileGrid data={{ grid: { strikes: [101, 100], grid: {} } }} spot={101} />);
  expect(profileRow(container, 100).querySelector('.volume-profile-cell').textContent).toBe('—');
  expect(profileRow(container, 100).textContent).not.toContain('AIR');
});

test('opposing complete expiry readings are not a low-pressure pocket merely because net sum is zero', () => {
  const data = { grid: { expiries: ['2026-10-02', '2026-10-09'], strikes: [101, 100], grid: { '2026-10-02': { 101: 1000, 100: 100 }, '2026-10-09': { 101: 1000, 100: -100 } } } };
  const { container } = render(<VolumeProfileGrid data={data} spot={101} />);
  expect(profileRow(container, 100).textContent).not.toContain('AIR');
});
