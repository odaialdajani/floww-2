import React, {useEffect, useState} from 'react';
import {render, screen, fireEvent, within} from '@testing-library/react';
import '@testing-library/jest-dom';
import ReviewInspector from './ReviewInspector';

function Contract({onMount}) {
  useEffect(() => { onMount(); }, [onMount]);
  const [value, setValue] = useState('');
  return <input aria-label="Contract note" value={value} onChange={e => setValue(e.target.value)}/>;
}
function inspector(props = {}) {
  return <ReviewInspector selectionKey="SPY|wall-1" wall={<p>Recorded wall facts</p>}
    contract={<p>Exact contract review</p>} flow={<button>Ask Flow</button>}
    publicAgent={<p>Draft only · activation unverified</p>} {...props}/>;
}

test('one inspector follows Wall, Contract, Flow and Public agent without duplicate visible panels', () => {
  render(inspector());
  const list = screen.getByRole('tablist', {name: 'Inspector sections'});
  expect(within(list).getAllByRole('tab').map(t => t.textContent)).toEqual(['Wall', 'Contract', 'Flow', 'Public agent']);
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  expect(screen.getByRole('tabpanel', {name: 'Wall'})).toHaveTextContent('Recorded wall facts');
  fireEvent.click(screen.getByRole('tab', {name: 'Public agent'}));
  expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
  expect(screen.getByRole('tabpanel', {name: 'Public agent'})).toHaveTextContent('activation unverified');
  expect(screen.queryByText(/Lodestar/)).toBeNull();
});

test('keyboard arrows wrap and Home/End activate the matching panel with focus', () => {
  render(inspector());
  const wall = screen.getByRole('tab', {name: 'Wall'});
  wall.focus();
  fireEvent.keyDown(wall, {key: 'ArrowLeft'});
  expect(screen.getByRole('tab', {name: 'Public agent'})).toHaveFocus();
  expect(screen.getByRole('tab', {name: 'Public agent'})).toHaveAttribute('aria-selected', 'true');
  fireEvent.keyDown(document.activeElement, {key: 'Home'});
  expect(wall).toHaveFocus();
  fireEvent.keyDown(wall, {key: 'ArrowRight'});
  expect(screen.getByRole('tab', {name: 'Contract'})).toHaveFocus();
  fireEvent.keyDown(document.activeElement, {key: 'End'});
  expect(screen.getByRole('tab', {name: 'Public agent'})).toHaveFocus();
});

test('tab switches preserve the mounted exact-contract state and do not repeat its read', () => {
  const onMount = jest.fn();
  render(inspector({contract: <Contract onMount={onMount}/>}));
  fireEvent.click(screen.getByRole('tab', {name: 'Contract'}));
  fireEvent.change(screen.getByLabelText('Contract note'), {target: {value: 'chosen exact option'}});
  fireEvent.click(screen.getByRole('tab', {name: 'Flow'}));
  fireEvent.click(screen.getByRole('tab', {name: 'Contract'}));
  expect(screen.getByLabelText('Contract note')).toHaveValue('chosen exact option');
  expect(onMount).toHaveBeenCalledTimes(1);
});

test('new selection resets the visible step instead of inheriting a previous wall handoff', () => {
  const view = render(inspector());
  fireEvent.click(screen.getByRole('tab', {name: 'Public agent'}));
  view.rerender(inspector({selectionKey: 'QQQ|wall-2'}));
  expect(screen.getByRole('tab', {name: 'Wall'})).toHaveAttribute('aria-selected', 'true');
});

test('opening contract review starts at Contract; tab activation alone never asks the assistant', () => {
  const ask = jest.fn();
  render(inspector({initialTab: 'contract', flow: <button onClick={ask}>Ask Flow</button>}));
  expect(screen.getByRole('tab', {name: 'Contract'})).toHaveAttribute('aria-selected', 'true');
  fireEvent.click(screen.getByRole('tab', {name: 'Flow'}));
  expect(ask).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Ask Flow'}));
  expect(ask).toHaveBeenCalledTimes(1);
});

test('two desks have unique accessible tab and panel identities', () => {
  const {container} = render(<>{inspector()}{inspector({selectionKey: 'QQQ|wall-2'})}</>);
  const ids = [...container.querySelectorAll('[id]')].map(e => e.id);
  expect(new Set(ids).size).toBe(ids.length);
  for (const tab of screen.getAllByRole('tab')) {
    expect(document.getElementById(tab.getAttribute('aria-controls'))).toHaveAttribute('aria-labelledby', tab.id);
  }
});
