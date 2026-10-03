import {cellPalette} from './SkylitHeatmapGrid';

test('continuous signed ramp selects readable text at every sampled color',()=>{
 for(let i=0;i<=100;i++){
  const palette=cellPalette(i/100);
  expect(palette.contrast).toBeGreaterThanOrEqual(4.5);
  expect(palette.background).toMatch(/^rgb\(/);
  expect(['#000','#fff']).toContain(palette.foreground);
 }
});
