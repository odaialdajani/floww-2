import React from 'react';
import {render,screen} from '@testing-library/react';
import SolsticeStatusStrip from './SolsticeStatusStrip';
import WallInspector from './WallInspector';
test('incomplete model data stays unknown even when vendor data is usable',()=>{
 const regime={sign:'UNKNOWN',reason:'MODEL_INPUTS_INCOMPLETE',modeled_at_spot:null,roots:[]};
 render(<><SolsticeStatusStrip isLive data={{gamma_regime_v1:regime,nodes:{regime:'negative'},quality:{state:'usable'}}}/><WallInspector wall={{wall_id:'test',low:98,high:105,members:[98,105]}} regime={regime}/></>);
 expect(screen.getByTestId('solstice-env')).toHaveTextContent('UNKNOWN');
 expect(screen.getByTestId('solstice-env')).toHaveTextContent('incomplete options data');
 expect(screen.getByText(/Options data is incomplete; no reliable sign/)).toBeInTheDocument();
 expect(screen.getByTestId('solstice-data')).toHaveTextContent('Data usable');
});
