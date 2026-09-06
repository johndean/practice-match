import type { Page } from '@playwright/test';

export interface CsScreen { name: string; viewport?: { width: number; height: number }; steps: (page: Page) => Promise<void>; }
const field = (p: Page) => p.getByLabel('Email address');
const notify = (p: Page) => p.getByRole('button', { name: 'Notify me', exact: true });
const redacted = (p: Page) => p.getByRole('button', { name: /^Redacted/ });
const MOBILE = { width: 390, height: 844 };

/** The approved states (spec §5): idle, invalid address, confirmed, teaser advanced twice — each
 *  captured at both the desktop viewport (the design's $preview, 1440×900) and the mobile viewport. */
const STATES: { name: string; steps: (page: Page) => Promise<void> }[] = [
  { name: 'idle', steps: async () => {} },
  { name: 'invalid', steps: async (p) => { await field(p).fill('nope'); await notify(p).click(); await p.getByText("That address doesn't look right").waitFor(); } },
  { name: 'done', steps: async (p) => { await field(p).fill('you@practice.com'); await notify(p).click(); await p.getByText("You're on the list").waitFor(); } },
  { name: 'tease-2', steps: async (p) => { await redacted(p).click(); await redacted(p).click(); await p.getByText('You can keep clicking. We admire the persistence.').waitFor(); } }
];

// The 4×2 product: cs-<state> at desktop, cs-mobile-<state> at 390×844 — eight screens total.
export const CS_SCREENS: CsScreen[] = STATES.flatMap((s) => [
  { name: `cs-${s.name}`, steps: s.steps },
  { name: `cs-mobile-${s.name}`, viewport: MOBILE, steps: s.steps }
]);
