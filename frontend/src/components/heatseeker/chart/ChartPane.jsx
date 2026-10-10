import React from 'react';
export default function ChartPane({ symbol, interval, children, status = 'live' }) {
  return (
    <div data-testid="chart-pane" data-symbol={symbol} data-interval={interval} data-status={status}>
      {children}
    </div>
  );
}
