import { fireEvent, getByTestId } from '@testing-library/react';

// Follow the same visible opener/tab path as a user, scoped to one pane.
export function openStockPanel(panel, container = document.body) {
  const opener = container.querySelector(`[data-testid="stock-dock-open-${panel}"]`);
  fireEvent.click(opener || getByTestId(container, `stock-inspector-tab-${panel}`));
}
