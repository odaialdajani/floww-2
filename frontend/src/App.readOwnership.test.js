/** @jest-environment jsdom */
// Execute the app's actual read effects without mounting broker/research UI.
// Only the transport is replaced. This keeps the test away from live data.
import { useEffect } from 'react';
import { act, renderHook } from '@testing-library/react';
import { buildHeatmapQuery, heatmapReadPath } from './lib/heatmapQuery';

const fs = require('fs');
const path = require('path');
const parser = require('@babel/parser');
const source = fs.readFileSync(process.env.FLOWW_POLLING_REVIEW_SOURCE || path.join(__dirname, 'App.js'), 'utf8');
const parsed = parser.parse(source, { sourceType: 'module', plugins: ['jsx'] });
const app = parsed.program.body.find(node => node.type === 'ExportDefaultDeclaration'
  && node.declaration.type === 'FunctionDeclaration').declaration;
const effects = app.body.body.filter(node => node.type === 'ExpressionStatement'
  && node.expression.type === 'CallExpression' && node.expression.callee.name === 'useEffect')
  .map(node => node.expression);

function effectFor(endpoint, env) {
  const effect = effects.find(node => source.slice(node.start, node.end).includes(endpoint));
  if (!effect) throw new Error('Missing app effect for ' + endpoint);
  const callback = source.slice(effect.arguments[0].start, effect.arguments[0].end);
  const dependencies = source.slice(effect.arguments[1].start, effect.arguments[1].end);
  return Function(...Object.keys(env), `return [${callback}, ${dependencies}];`)(...Object.values(env));
}

function environment() {
  return {
    API: '/api', ticker: 'SPY', refreshMs: 25000,
    debouncedExpiries: 4, debouncedMode: 'day', debouncedDte: null, effectiveExpiryScope: 'loaded',
    buildHeatmapQuery, heatmapReadPath, fetchGen: { current: 0 },
    axios: { get: jest.fn(async () => ({ data: { ticker: 'SPY', spot: 100 } })), isCancel: () => false },
    setData: jest.fn(), setErr: jest.fn(), setLoading: jest.fn(),
    setAdvanced: jest.fn(), setAdvancedLoading: jest.fn(), setAdvancedError: jest.fn(),
    setLivespot: jest.fn(), setEnsembleData: jest.fn(),
  };
}

function useActualEffect(endpoint, env, page) {
  const [callback, dependencies] = effectFor(endpoint, { ...env, page });
  useEffect(callback, dependencies); // production effect and dependency values
}

beforeEach(() => { jest.useFakeTimers(); });
afterEach(() => { jest.useRealTimers(); });

test.each([
  ['heatmapReadPath', 'trinity'],
  ['/advanced/', 'heatseeker'],
  ['/spot/', 'trinity'],
])('%s makes no root requests on %s where it has no consumer', async (endpoint, page) => {
  const env = environment();
  const { unmount } = renderHook(() => useActualEffect(endpoint, env, page));
  await act(async () => { jest.advanceTimersByTime(60000); });
  expect(env.axios.get).not.toHaveBeenCalled();
  unmount();
});

test('leaving Stock chart aborts its map read and stops its timer', async () => {
  const env = environment();
  env.axios.get.mockImplementation(() => new Promise(() => {}));
  const { rerender, unmount } = renderHook(({ page }) => useActualEffect('heatmapReadPath', env, page),
    { initialProps: { page: 'heatseeker' } });
  expect(env.axios.get).toHaveBeenCalledTimes(1);
  const signal = env.axios.get.mock.calls[0][1].signal;
  rerender({ page: 'trinity' });
  expect(signal.aborted).toBe(true);
  await act(async () => { jest.advanceTimersByTime(60000); });
  expect(env.axios.get).toHaveBeenCalledTimes(1);
  unmount();
});

test('Stock chart still receives the owning map scope and result', async () => {
  const env = environment();
  const { unmount } = renderHook(() => useActualEffect('heatmapReadPath', env, 'heatseeker'));
  await act(async () => {});
  expect(env.axios.get.mock.calls[0][0]).toBe('/api/data/SPY?expiries=4&mode=day');
  expect(env.setData).toHaveBeenCalledWith({ ticker: 'SPY', spot: 100 });
  unmount();
});
