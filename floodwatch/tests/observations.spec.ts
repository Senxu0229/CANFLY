import { test, expect, type Page } from '@playwright/test';

async function ready(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Kalari Abdu', exact: true })).toBeVisible();
  const map = page.getByTestId('comparison-map');
  await expect(map).toHaveAttribute('data-before-loaded', 'true');
  await expect(map).toHaveAttribute('data-after-loaded', 'true');
  return map;
}

test('real imagery loads without external services and supports comparison controls', async ({ page }) => {
  const unexpectedRequests: string[] = [];
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      if (url.hostname !== '127.0.0.1' || url.pathname.startsWith('/data/')) {
        unexpectedRequests.push(url.href);
        await route.abort();
        return;
      }
    }
    await route.continue();
  });
  const map = await ready(page);
  const dates = page.getByRole('region', { name: 'Acquisition dates' });
  await expect(dates).toContainText('28 Aug 2024');
  await expect(dates).toContainText(/21 Sept? 2024/);
  await expect(dates).toContainText('13 days before');
  await expect(dates).toContainText('11 days after');
  await expect(page.getByLabel('Background map')).toHaveValue('plain');
  await expect(map.locator('canvas')).toHaveCount(2);

  const divider = page.getByRole('slider', { name: 'Before and after divider' });
  await divider.focus();
  await divider.press('ArrowRight');
  await expect(divider).toHaveAttribute('aria-valuenow', '51');
  await divider.press('Home');
  await expect(divider).toHaveAttribute('aria-valuenow', '0');
  await divider.press('End');
  await expect(divider).toHaveAttribute('aria-valuenow', '100');

  const modes = page.getByRole('group', { name: 'Observation view' });
  await modes.getByRole('button', { name: 'Before', exact: true }).click();
  await expect(map).toHaveAttribute('data-mode', 'before');
  await expect(divider).toBeHidden();
  const initialMarker = await map.locator('.map-after .village-marker').boundingBox();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  const bounds = (await map.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width * 0.35, bounds.y + bounds.height * 0.35);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * 0.35 + 70, bounds.y + bounds.height * 0.35 + 35, { steps: 10 });
  await page.mouse.up();
  await expect.poll(async () => {
    const marker = await map.locator('.map-after .village-marker').boundingBox();
    return Math.abs(marker!.x - initialMarker!.x);
  }).toBeGreaterThan(40);
  await expect.poll(async () => {
    const before = (await map.locator('.map-before .village-marker').boundingBox())!;
    const after = (await map.locator('.map-after .village-marker').boundingBox())!;
    return Math.abs(before.x - after.x) + Math.abs(before.y - after.y);
  }).toBeLessThan(1);
  await page.getByRole('button', { name: 'Reset to study area' }).click();
  await modes.getByRole('button', { name: 'After', exact: true }).click();
  await expect(map).toHaveAttribute('data-mode', 'after');
  await modes.getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(divider).toBeVisible();
  await page.getByLabel('Show study boundary').uncheck();
  await expect(page.getByLabel('Show study boundary')).not.toBeChecked();
  await page.getByLabel('Show study boundary').check();

  await expect(page.getByRole('heading', { name: /recovery priorities|affected buildings|days to dry/i })).toHaveCount(0);
  await page.getByText('Data sources and processing notes', { exact: true }).click();
  await expect(page.getByText(/brightness differences are not measurements of flooding/)).toBeVisible();
  const timeline = (await page.getByRole('region', { name: 'Observation timeline' }).boundingBox())!;
  const notes = (await page.locator('.source-details').boundingBox())!;
  expect(timeline.y + timeline.height).toBeLessThanOrEqual(notes.y + 1);
  expect(unexpectedRequests).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('mobile viewport retains readable map and working before/after controls', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const map = await ready(page);
  await map.scrollIntoViewIfNeeded();
  const size = await map.boundingBox();
  expect(size?.width).toBeGreaterThan(280);
  expect(size?.height).toBeGreaterThan(250);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const modes = page.getByRole('group', { name: 'Observation view' });
  await modes.getByRole('button', { name: 'After', exact: true }).click();
  await expect(map).toHaveAttribute('data-mode', 'after');
  await modes.getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(page.getByRole('slider', { name: 'Before and after divider' })).toBeVisible();
});

test('missing real manifest shows a recoverable error without mock fallback', async ({ page }) => {
  await page.route('**/observations/manifest.json', (route) => route.fulfill({ status: 404, body: 'Missing' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Observation data could not be loaded');
  await expect(page.getByTestId('comparison-map')).toHaveCount(0);
  await page.unroute('**/observations/manifest.json');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByTestId('comparison-map')).toHaveAttribute('data-before-loaded', 'true');
});

test('a missing observation image is reported instead of rendering an incomplete comparison', async ({ page }) => {
  await page.route('**/observations/radar_20240921*.png', (route) => route.fulfill({ status: 404, body: 'Missing' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Observation data could not be loaded');
  await expect(page.getByTestId('comparison-map')).toHaveCount(0);
});

test('unavailable optional basemap does not replace the local radar comparison', async ({ page }) => {
  await page.route('https://tile.openstreetmap.org/**', (route) => route.abort());
  const map = await ready(page);
  await page.getByLabel('Background map').selectOption('streets');
  await expect(page.getByText(/Background tiles unavailable/)).toBeVisible();
  await expect(page.getByText('Map unavailable', { exact: true })).toHaveCount(0);
  await expect(map).toHaveAttribute('data-before-loaded', 'true');
  await expect(map).toHaveAttribute('data-after-loaded', 'true');
  await page.getByLabel('Background map').selectOption('plain');
  await expect(page.getByText(/Background tiles unavailable/)).toHaveCount(0);
});
