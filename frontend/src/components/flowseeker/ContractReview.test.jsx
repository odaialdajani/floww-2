import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react';
import ContractReview from './ContractReview';

test('manual checks and review status belong to the selected contract only', () => {
 const {rerender}=render(<ContractReview contractKey="SPY|call|500|2026-10-02"/>);
 const item=screen.getByLabelText('Checked quote age and missing fields');
 fireEvent.click(item);
 fireEvent.click(screen.getByText('Mark reviewed'));
 expect(screen.getByRole('status')).toHaveTextContent('Reviewed');
 rerender(<ContractReview contractKey="SPY|put|500|2026-10-02"/>);
 expect(screen.getByLabelText('Checked quote age and missing fields')).not.toBeChecked();
 expect(screen.queryByRole('status')).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Skip review'));
 rerender(<ContractReview contractKey="SPY|call|500|2026-10-02"/>);
 expect(screen.getByLabelText('Checked quote age and missing fields')).toBeChecked();
 expect(screen.getByRole('status')).toHaveTextContent('Reviewed');
 fireEvent.click(screen.getByLabelText('Checked quote age and missing fields'));
 expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
