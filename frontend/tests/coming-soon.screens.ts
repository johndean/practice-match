import type { Page } from '@playwright/test';

export interface CsScreen { name: string; viewport?: { width: number; height: number }; steps: (page: Page) => Promise<void>; }
const field = (p: Page) => p.getByLabel('Email address');
const notify = (p: Page) => p.getByRole('button', { name: 'Notify me', exact: true });
const redacted = (p: Page) => p.getByRole('button', { name: /^Redacted/ });

/** The approved states (spec §5): idle, invalid address, confirmed, teaser advanced twice, and mobile. */
export const CS_SCREENS: CsScreen[] = [
  { name: 'cs-idle', steps: async () => {} },
  { name: 'cs-invalid', steps: async (p) => { await field(p).fill('nope'); await notify(p).click(); await p.getByText("That address doesn't look right").waitFor(); } },
  { name: 'cs-done', steps: async (p) => { await field(p).fill('you@practice.com'); await notify(p).click(); await p.getByText("You're on the list").waitFor(); } },
  { name: 'cs-tease-2', steps: async (p) => { await redacted(p).click(); await redacted(p).click(); await p.getByText('You can keep clicking. We admire the persistence.').waitFor(); } },
  { name: 'cs-mobile', viewport: { width: 390, height: 844 }, steps: async () => {} }
];
