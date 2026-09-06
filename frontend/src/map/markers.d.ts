// Type declarations for the plain-JS marker builders in markers.js. Kept separate so
// markers.js itself stays byte-identical to the ported prototype code (no JSDoc added).

export function pricePin(label: string, active: boolean): string;
export function dot(size: number, color: string, border?: string): string;

export function practicePin(label: string, selected: boolean): string;
export function practiceCallout(p: { name: string; priceLabel: string; meta?: string; photoSrc?: string }): string;
