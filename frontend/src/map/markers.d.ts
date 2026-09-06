// Type declarations for the plain-JS marker builders in markers.js. Kept separate so
// markers.js itself stays byte-identical to the ported prototype code (no JSDoc added).

export interface MarkerLike { id: string; lat: number; lng: number; [key: string]: unknown }
export interface ClusterEntry { kind: 'pin' | 'cluster'; m?: MarkerLike; lat?: number; lng?: number; count?: number; ids?: string[] }

export function pill(label: string, active: boolean, muted?: boolean): string;
export function clusterIcon(count: number): string;
export function clusterize(markers: MarkerLike[], zoom: number): ClusterEntry[];
export function pricePin(label: string, active: boolean): string;
export function dot(size: number, color: string, border?: string): string;

export function practicePin(label: string, selected: boolean): string;
export function practiceCallout(p: { name: string; priceLabel: string; meta?: string; photoSrc?: string }): string;
