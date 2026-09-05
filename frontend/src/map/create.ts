import type { MapEngine } from './engine';
export async function createEngine(): Promise<MapEngine> {
  const { LeafletMapEngine } = await import('./engines/leaflet');
  return new LeafletMapEngine();
}
