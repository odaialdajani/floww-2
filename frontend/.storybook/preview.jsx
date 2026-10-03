import '../src/index.css';
import '../src/components/heatseeker/SolsticeWorkspace.css';

export default {
  tags: ['autodocs'],
  parameters: {
    layout: 'padded',
    a11y: { test: 'error' },
    backgrounds: { options: { solstice: { name: 'Solstice', value: '#080b10' } } },
  },
  initialGlobals: { backgrounds: { value: 'solstice' } },
};
