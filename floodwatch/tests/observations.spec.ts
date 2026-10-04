import { test, expect, type Page } from '@playwright/test';

async function ready(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('combobox', { name: 'Location', exact: true })).toHaveValue('Kalari Abdu');
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

  const divider = page.getByRole('slider', { name: 'Left and right divider' });
  await divider.focus();
  await divider.press('ArrowRight');
  await expect(divider).toHaveAttribute('aria-valuenow', '51');
  await divider.press('Home');
  await expect(divider).toHaveAttribute('aria-valuenow', '0');
  await divider.press('End');
  await expect(divider).toHaveAttribute('aria-valuenow', '100');

  const modes = page.getByRole('group', { name: 'Observation view' });
  await modes.getByRole('button', { name: 'Left only', exact: true }).click();
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
  await modes.getByRole('button', { name: 'Right only', exact: true }).click();
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
  await modes.getByRole('button', { name: 'Right only', exact: true }).click();
  await expect(map).toHaveAttribute('data-mode', 'after');
  await modes.getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(page.getByRole('slider', { name: 'Left and right divider' })).toBeVisible();
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

test('candidate-change view uses the real report and distinguishes new water from net change', async ({ page }) => {
  const manifest = await (await page.request.get('/observations/manifest.json')).json();
  const report = await (await page.request.get('/' + manifest.analysis_url)).json();
  const map = await ready(page);
  await expect(page.getByTestId('new-water-area')).toContainText(report.areas.new_water_km2.toFixed(2));
  await expect(page.getByText('Difference between dates', { exact: true }).locator('..')).toContainText(report.areas.net_water_change_km2.toFixed(2));
  await page.getByRole('group', { name: 'Observation view' }).getByRole('button', { name: 'Changes', exact: true }).click();
  await expect(map).toHaveAttribute('data-mode', 'change');
  await expect(page.getByLabel('Candidate change legend')).toBeVisible();
  await expect(page.getByLabel('Candidate change legend')).toContainText('Orange: brighter in September; water loss is unconfirmed.');
  await expect(page.getByText(/This is the light-blue area, not confirmed flooding/)).toBeVisible();
  await expect(page.getByRole('slider', { name: 'Left and right divider' })).toBeHidden();
  await expect(page.getByText(/Actual flooding may lie outside this range/)).toBeVisible();
  await page.getByText('Method and downloads', { exact: true }).click();
  await expect(page.getByTestId('analysis-revision')).toContainText(report.method.threshold_db.toFixed(1) + ' dB');
  if (report.otsu_reference && report.method.threshold_db !== report.otsu_reference.threshold_db) {
    await expect(page.getByTestId('threshold-comparison')).toContainText(report.otsu_reference.areas.lost_water_km2.toFixed(2));
  } else {
    await expect(page.getByTestId('threshold-comparison')).toHaveCount(0);
  }
  await expect(page.getByText(/Product calibration →/)).toContainText(report.method.threshold_method);
  const download = page.getByRole('link', { name: 'Change classes GeoTIFF' });
  await expect(download).toHaveAttribute('href', new URL(report.downloads.classes, page.url()).href);
  const response = await page.request.get(await download.getAttribute('href') as string);
  expect(response.ok()).toBeTruthy();
  expect((await response.body()).length).toBeGreaterThan(1000);
  await page.getByRole('group', { name: 'Observation view' }).getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(page.getByLabel('Candidate change legend')).toHaveCount(0);
});

test('missing analysis or inconsistent areas fail clearly instead of showing invented numbers', async ({ page }) => {
  await page.route('**/observations/analysis_report_*.json', (route) => route.fulfill({ status: 404, body: 'Missing analysis' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Observation data could not be loaded');
  await expect(page.getByTestId('new-water-area')).toHaveCount(0);
  await page.unroute('**/observations/analysis_report_*.json');
  await page.route('**/observations/analysis_report_*.json', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.areas.new_water_km2 += 100;
    await route.fulfill({ json: data });
  });
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('alert')).toContainText('water analysis is missing, inconsistent');
});

test('missing candidate overlay is reported', async ({ page }) => {
  await page.route('**/observations/water_change_*.png', (route) => route.fulfill({ status: 404, body: 'Missing' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Observation data could not be loaded');
});

async function pairReady(page: Page, left: string, right: string) {
  const map = page.getByTestId('comparison-map');
  await expect(page.getByLabel('Left image', { exact: true })).toHaveValue(left);
  await expect(page.getByLabel('Right image', { exact: true })).toHaveValue(right);
  await expect(map).toHaveAttribute('data-left-id', left);
  await expect(map).toHaveAttribute('data-right-id', right);
  await expect(map).toHaveAttribute('data-before-loaded', 'true');
  await expect(map).toHaveAttribute('data-after-loaded', 'true');
  return map;
}

test('four dates, arbitrary pairs, swapping and quick comparisons keep the map and guard analysis', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const map = await ready(page);
  const left = page.getByLabel('Left image', { exact: true });
  const right = page.getByLabel('Right image', { exact: true });
  await expect(left.locator('option')).toHaveCount(4);
  await expect(right.locator('option')).toHaveCount(4);
  await expect(left.locator('option[value="20240921"]')).toBeDisabled();
  await expect(right.locator('option[value="20240828"]')).toBeDisabled();
  const quick = page.getByRole('group', { name: 'Quick comparisons' });
  await expect(quick.getByRole('button')).toHaveCount(3);
  const modes = page.getByRole('group', { name: 'Observation view' });
  await modes.getByRole('button', { name: 'Changes', exact: true }).click();
  await expect(page.getByTestId('new-water-area')).toBeVisible();

  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  const bounds = (await map.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width * .35, bounds.y + bounds.height * .35);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * .35 + 60, bounds.y + bounds.height * .35 + 30, { steps: 10 });
  await page.mouse.up();
  // Stop map inertia with a click; switching dates must retain this camera.
  await map.locator('.map-after canvas').click({ position: { x: 100, y: 100 } });
  const position = (await map.locator('.map-after .village-marker').boundingBox())!;
  const canvasBefore = await map.locator('.map-after canvas').screenshot();
  await quick.getByRole('button').nth(1).click();
  await pairReady(page, '20240921', '20241015');
  await expect(map).toHaveAttribute('data-mode', 'compare');
  await expect(modes.getByRole('button', { name: 'Changes', exact: true })).toBeDisabled();
  await expect(page.getByTestId('new-water-area')).toHaveCount(0);
  await expect(page.getByLabel('Candidate change legend')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Image comparison only' })).toBeVisible();
  await expect.poll(async () => {
    const now = (await map.locator('.map-after .village-marker').boundingBox())!;
    return Math.abs(now.x - position.x) + Math.abs(now.y - position.y);
  }).toBeLessThan(1);
  const canvasAfter = await map.locator('.map-after canvas').screenshot();
  expect(canvasAfter.equals(canvasBefore)).toBe(false);

  await quick.getByRole('button').nth(2).click();
  await pairReady(page, '20241015', '20241108');
  await left.selectOption('20240828');
  await pairReady(page, '20240828', '20241108');
  await page.getByRole('button', { name: 'Swap sides', exact: true }).click();
  await pairReady(page, '20241108', '20240828');
  await expect(map.locator('.map-date.before')).toContainText('8 Nov 2024');
  await expect(map.locator('.map-date.after')).toContainText('28 Aug 2024');

  await quick.getByRole('button').nth(0).click();
  await pairReady(page, '20240828', '20240921');
  await expect(page.getByTestId('new-water-area')).toBeVisible();
  await page.getByRole('button', { name: 'Swap sides', exact: true }).click();
  await pairReady(page, '20240921', '20240828');
  await expect(page.getByTestId('new-water-area')).toHaveCount(0);
  await expect(modes.getByRole('button', { name: 'Changes', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'View analysed pair', exact: true }).click();
  await pairReady(page, '20240828', '20240921');
  await expect(modes.getByRole('button', { name: 'Changes', exact: true })).toBeEnabled();
  expect(errors).toEqual([]);
});

test('mobile date selection and fast switches finish on the requested pair', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await ready(page);
  const quick = page.getByRole('group', { name: 'Quick comparisons' });
  await quick.getByRole('button').nth(2).click();
  await quick.getByRole('button').nth(0).click();
  await quick.getByRole('button').nth(1).click();
  const map = await pairReady(page, '20240921', '20241015');
  await page.getByLabel('Right image', { exact: true }).selectOption('20241108');
  await pairReady(page, '20240921', '20241108');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect((await map.boundingBox())!.height).toBeGreaterThan(280);
  await expect(page.getByRole('slider', { name: 'Left and right divider' })).toBeVisible();
});

test('missing new-date imagery and invalid analysis dates are reported', async ({ page }) => {
  await page.route('**/observations/radar_20241108*.png', (route) => route.fulfill({ status: 404, body: 'Missing November image' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('2024-11-08');
  await page.unroute('**/observations/radar_20241108*.png');
  await page.route('**/observations/analysis_report_*.json', async (route) => {
    const response = await route.fetch();
    const report = await response.json();
    report.dates = ['20240828', '20990101'];
    await route.fulfill({ json: report });
  });
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('alert')).toContainText('water analysis is missing, inconsistent');
});
