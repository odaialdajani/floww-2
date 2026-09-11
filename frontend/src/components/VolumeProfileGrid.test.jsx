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
