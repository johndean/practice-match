import type { Page } from '@playwright/test';
import { btn, click, jump, waitMap } from './harness';

export interface Screen {
  name: string;
  viewport?: { width: number; height: number }; // default 1440×940 from the config
  steps: (page: Page) => Promise<void>;         // identical clicks on reference and app, from the gate
}

const browse = async (p: Page) => { await jump(p, 'Browse'); await waitMap(p); };
const market = async (p: Page) => { await browse(p); await click(p, 'Market Data'); await waitMap(p); };
const wizard = async (p: Page) => { await jump(p, 'Seller'); await click(p, 'Create a listing'); };
const admin = async (p: Page) => { await jump(p, 'Admin'); };
const mobile = async (p: Page) => { await click(p, 'Mobile view'); await jump(p, 'Browse'); };

export const SCREENS: Screen[] = [
  { name: 'gate-signin', steps: async () => {} },
  { name: 'gate-apply', steps: async (p) => { await click(p, 'Request access'); } },
  { name: 'gate-pending', steps: async (p) => { await click(p, 'Pending approval'); } },
  { name: 'gate-declined', steps: async (p) => { await click(p, 'Request declined'); } },
  { name: 'browse-listings', steps: browse },
  { name: 'browse-market', steps: market },
  { name: 'browse-market-layers-closed', steps: async (p) => { await market(p); await click(p, 'Data Layers'); } },
  { name: 'browse-market-panel', steps: async (p) => { await market(p); await p.getByText('Cedar Park').first().click(); await p.waitForTimeout(400); } },
  { name: 'detail', steps: async (p) => { await jump(p, 'Listing'); } },
  // The jump bar's default listing (Cedar Park / p1) always carries a pre-seeded pending
  // request in the prototype's demo data (logic.js `state.requests`), so it never shows
  // "I'm interested" — only "Request sent". Open a listing with no seeded request instead
  // (Round Rock / p2) via the Browse Listings card, which does show the button.
  { name: 'interest-modal', steps: async (p) => { await browse(p); await p.getByText('Round Rock').first().click(); await click(p, "I'm interested"); } },
  { name: 'requests', steps: async (p) => { await jump(p, 'Requests'); } },
  { name: 'seller-dash', steps: async (p) => { await jump(p, 'Seller'); } },
  { name: 'wizard-step-1', steps: wizard },
  { name: 'wizard-step-7', steps: async (p) => { await wizard(p); await btn(p, /^7/).click(); } },
  { name: 'wizard-preview', steps: async (p) => { await wizard(p); await btn(p, /^8/).click(); } },
  { name: 'wizard-done', steps: async (p) => { await wizard(p); await btn(p, /^8/).click(); await click(p, 'Submit for review'); } },
  { name: 'admin-users', steps: admin },
  { name: 'admin-listings', steps: async (p) => { await admin(p); await btn(p, /^Listings\s*\d/).click(); } },
  { name: 'admin-requests', steps: async (p) => { await admin(p); await btn(p, /^Requests\s*\d/).click(); } },
  { name: 'admin-data-sources', steps: async (p) => { await admin(p); await btn(p, /^Data Sources\s*\d/).click(); } },
  { name: 'mobile-list', steps: mobile },
  { name: 'mobile-map', steps: async (p) => { await mobile(p); await click(p, 'Map'); await waitMap(p); } },
  { name: 'mobile-detail', steps: async (p) => { await mobile(p); await p.getByText('Cedar Park').first().click(); } },
  { name: 'header-1100', viewport: { width: 1100, height: 940 }, steps: browse },
  { name: 'header-1000', viewport: { width: 1000, height: 940 }, steps: browse }
];
