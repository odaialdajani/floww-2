import React,{StrictMode} from 'react';
import {act,render,screen} from '@testing-library/react';
import useScreenContext,{publishScreenContext,usePublishScreenContext} from './useScreenContext';
function Read(){const [value]=useScreenContext();return <span data-testid='selection'>{value.ticker || 'none'}</span>}
function Publish({context}){usePublishScreenContext(context);return null}
test('same-value ownership handoff survives old release and current owner clears',()=>{
 const releaseOld=publishScreenContext({ticker:'SPY'});
 render(<Read/>);
 let releaseNew;act(()=>{releaseNew=publishScreenContext({ticker:'SPY'});});
 act(()=>releaseOld());expect(screen.getByTestId('selection')).toHaveTextContent('SPY');
 act(()=>releaseNew());expect(screen.getByTestId('selection')).toHaveTextContent('none');
});
test('publisher survives strict mode, updates, deactivation, and unmount',()=>{
 const view=render(<StrictMode><Publish context={{ticker:'SPY'}}/><Read/></StrictMode>);
 expect(screen.getByTestId('selection')).toHaveTextContent('SPY');
 view.rerender(<StrictMode><Publish context={{ticker:'QQQ'}}/><Read/></StrictMode>);
 expect(screen.getByTestId('selection')).toHaveTextContent('QQQ');
 view.rerender(<StrictMode><Publish context={null}/><Read/></StrictMode>);
 expect(screen.getByTestId('selection')).toHaveTextContent('none');
 view.rerender(<StrictMode><Publish context={{ticker:'NVDA'}}/><Read/></StrictMode>);
 expect(screen.getByTestId('selection')).toHaveTextContent('NVDA');
 view.rerender(<StrictMode><Read/></StrictMode>);
 expect(screen.getByTestId('selection')).toHaveTextContent('none');
});
