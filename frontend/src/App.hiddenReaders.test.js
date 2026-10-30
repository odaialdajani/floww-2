/** @jest-environment jsdom */
import React, { useEffect } from 'react';
import { render } from '@testing-library/react';

const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');
const parser = require('@babel/parser');
const source = fs.readFileSync(path.join(__dirname, 'App.js'), 'utf8');
const tree = parser.parse(source, { sourceType: 'module', plugins: ['jsx'] });

function actualReader(name, env) {
  let expression;
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'JSXExpressionContainer' && source.slice(node.start, node.end).includes(`<${name} `)) {
      expression = source.slice(node.expression.start, node.expression.end);
    }
    Object.values(node).forEach(value => Array.isArray(value) ? value.forEach(walk) : walk(value));
  }
  walk(tree);
  if (!expression) throw new Error(`Missing reader ${name}`);
  const code = babel.transformSync(`return (${expression});`, {
    babelrc: false, configFile: false, parserOpts: { allowReturnOutsideFunction: true },
    plugins: ['@babel/plugin-transform-react-jsx'],
  }).code;
  return Function('React', ...Object.keys(env), code)(React, ...Object.values(env));
}

test.each(['Movers', 'SolsticeLeaderboard'])('%s starts only when its owning rail is open', name => {
  const startRead = jest.fn();
  const stopRead = jest.fn();
  function Reader() { useEffect(() => { startRead(); return stopRead; }, []); return null; }
  const env = { [name]: Reader, showLeftSidebar: false, heatmapReplay: false,
    analyticalRangeOpen: false, setTicker: jest.fn(), dte: null };
  const { rerender } = render(actualReader(name, env));
  expect(startRead).not.toHaveBeenCalled();
  rerender(actualReader(name, { ...env, showLeftSidebar: true }));
  expect(startRead).toHaveBeenCalledTimes(1);
  rerender(actualReader(name, env));
  expect(stopRead).toHaveBeenCalledTimes(1);
});
