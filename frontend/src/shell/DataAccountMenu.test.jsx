import React from 'react';
import {fireEvent,render,screen} from '@testing-library/react';
import DataAccountMenu from './DataAccountMenu';
test('account action remains reachable in a quiet menu without a blinking connection claim',()=>{
 const signOut=jest.fn();const view=render(<DataAccountMenu ticker="SPY" data={{ticker:'SPY',data_source:'public_api',event_time:'2026-10-06T14:00:00Z'}} onSignOut={signOut}/>);const menu=screen.getByLabelText('Data and account settings').closest('details');menu.open=true;expect(screen.getByText('public api')).toBeVisible();fireEvent.click(screen.getByRole('button',{name:'Sign out'}));expect(signOut).toHaveBeenCalledTimes(1);expect(view.container.querySelector('.dot')).toBeNull();
});
test('a delayed reading for another stock cannot become the selected stock source or clock',()=>{
 render(<DataAccountMenu ticker="QQQ" data={{ticker:'SPY',data_source:'old-source',event_time:'2026-10-06T14:00:00Z'}}/>);expect(screen.getByText('Source unavailable')).toBeInTheDocument();expect(screen.getByText('Time unavailable')).toBeInTheDocument();expect(screen.queryByText('old source')).not.toBeInTheDocument();
});
test('Escape closes the menu and returns keyboard focus to its one shared control',()=>{
 render(<DataAccountMenu ticker="SPY"/>);const toggle=screen.getByLabelText('Data and account settings'),menu=toggle.closest('details');menu.open=true;fireEvent.keyDown(menu,{key:'Escape'});expect(menu.open).toBe(false);expect(toggle).toHaveFocus();
});
