import '../src/index.css';
import '../src/components/heatseeker/SolsticeWorkspace.css';
import '../src/NeutralTheme.css';

export default {
  tags: ['autodocs'],
  parameters: {
    layout: 'padded',
    a11y: { test: 'error' },
    backgrounds: { options: { solstice: { name: 'Solstice', value: '#090909' } } },
  },
  initialGlobals: { backgrounds: { value: 'solstice' } },
};
