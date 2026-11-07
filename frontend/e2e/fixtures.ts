import { test as base, request as pwRequest, type APIRequestContext } from '@playwright/test';
import fs from 'fs';
import path from 'path';

export type Role = 'buyer' | 'seller' | 'dealer' | 'staff' | 'broker' | 'fakeadmin';

export const storageStatePath = (role: Role) => path.join(__dirname, '.auth', `${role}.json`);

type Fixtures = {
  /** API-контекст з токеном ролі (Bearer — без cookie, тож CSRF не потрібен). */
  api: (role: Role) => Promise<APIRequestContext>;
  /** Унікальний email на тестовому домені. */
  uniqueEmail: string;
  /** Шлях до storageState ролі: test.use({ storageState: storageStatePath('buyer') }). */
  asRole: (role: Role) => string;
};

type StoredCookie = { name: string; value: string };

export const test = base.extend<Fixtures>({
  api: async ({ baseURL }, use) => {
    const contexts: APIRequestContext[] = [];
    await use(async (role) => {
      const state = JSON.parse(fs.readFileSync(storageStatePath(role), 'utf-8'));
      // Значення httpOnly-cookie access — той самий JWT, що приймає заголовок Bearer.
      const access = (state.cookies ?? []).find((c: StoredCookie) => c.name === 'access')?.value;
      const ctx = await pwRequest.newContext({
        baseURL,
        extraHTTPHeaders: access ? { Authorization: `Bearer ${access}` } : {},
      });
      contexts.push(ctx);
      return ctx;
    });
    await Promise.all(contexts.map((c) => c.dispose()));
  },
  // eslint-disable-next-line no-empty-pattern
  uniqueEmail: async ({}, use, testInfo) => {
    await use(`e2e-${Date.now()}-${testInfo.workerIndex}@e2e.test`);
  },
  // eslint-disable-next-line no-empty-pattern
  asRole: async ({}, use) => {
    await use(storageStatePath);
  },
});

export { expect } from '@playwright/test';
