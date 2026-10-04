import { test, expect, type Page } from '@playwright/test';

type ChatRequest = {
  message: string;
  history: { role: 'user' | 'assistant'; content: string }[];
  context: { left_id: string; right_id: string; view_mode: string };
};

const answer = {
  answer: 'Observation: light blue marks possible new water. [S1]\nInterpretation: flooding is unconfirmed.',
  citations: [{ id: 'S1', title: 'Water detection method', url: '/api/sources/water-method', excerpt: 'Both dates use the same threshold.' }],
  retrieval_count: 1,
};

async function openChat(page: Page) {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Ask AI', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Ask AI', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Map assistant', exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

test('assistant sends current map context, retains bounded history and shows safe source citations', async ({ page }) => {
  const requests: ChatRequest[] = [];
  await page.route('**/api/chat', async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: { ...answer, answer: answer.answer + '\n<img src=x onerror="alert(1)">', citations: [...answer.citations, { id: 'S2', title: 'Unsafe external source', url: 'javascript:alert(1)', excerpt: 'This must not be a link.' }] } });
  });
  const dialog = await openChat(page);
  await expect(dialog.getByLabel('Ask about this map')).toBeFocused();
  await dialog.getByRole('button', { name: 'How is possible new water detected?' }).click();
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toContainText('Interpretation: flooding is unconfirmed.');
  expect(requests[0]).toEqual({ message: 'How is possible new water detected?', history: [], context: { left_id: '20240828', right_id: '20240921', view_mode: 'compare' } });
  await expect(dialog.getByRole('link', { name: /Water detection method/ })).toHaveAttribute('href', 'http://127.0.0.1:4173/api/sources/water-method');
  await dialog.getByText('View evidence', { exact: true }).first().click();
  await expect(dialog.getByText('Both dates use the same threshold.')).toBeVisible();
  await expect(dialog.getByRole('link', { name: /Unsafe external/ })).toHaveCount(0);
  await expect(dialog.locator('img')).toHaveCount(0);
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toContainText('<img src=x onerror="alert(1)">');

  // Closing preserves completed exchanges; it does not send a request.
  await dialog.getByRole('button', { name: 'Close assistant' }).click();
  await expect(page.getByRole('button', { name: 'Ask AI', exact: true })).toBeFocused();
  await page.getByRole('group', { name: 'Observation view' }).getByRole('button', { name: 'Changes', exact: true }).click();
  await page.getByRole('button', { name: 'Ask AI', exact: true }).click();
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toHaveCount(1);
  for (let i = 1; i <= 4; i++) {
    await dialog.getByLabel('Ask about this map').fill(`Follow-up ${i}`);
    await dialog.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toHaveCount(i + 1);
  }
  expect(requests[4].history).toHaveLength(6);
  expect(requests[4].history[0].content).toBe('Follow-up 1');
  expect(requests[4].context.view_mode).toBe('change');
  await dialog.getByLabel('Ask about this map').press('Escape');
  await expect(dialog).toBeHidden();
});

test('assistant reports service errors, preserves the question and permits a real retry', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/chat', async (route) => {
    attempts++;
    await route.fulfill(attempts === 1 ? { status: 503, json: { detail: 'Model unavailable' } } : { json: answer });
  });
  const dialog = await openChat(page);
  const question = dialog.getByLabel('Ask about this map');
  await question.fill('Which satellite acquired these images?');
  await question.press('Enter');
  await expect(dialog.getByRole('alert')).toContainText('assistant service is unavailable');
  await expect(question).toHaveValue('Which satellite acquired these images?');
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toHaveCount(0);
  await dialog.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toContainText(answer.answer);
  await expect(dialog.getByRole('alert')).toHaveCount(0);
  expect(attempts).toBe(2);
});

test('date changes abort pending answers and clear conversation context before another request', async ({ page }) => {
  let release!: () => void;
  let finished!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  const responded = new Promise<void>((resolve) => { finished = resolve; });
  const requests: ChatRequest[] = [];
  await page.route('**/api/chat', async (route) => {
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) {
      await delayed;
      try { await route.fulfill({ json: { ...answer, answer: 'STALE ANSWER FROM AUGUST PAIR' } }); } catch { /* The browser aborted it. */ }
      finished();
    } else await route.fulfill({ json: answer });
  });
  const dialog = await openChat(page);
  await dialog.getByRole('button', { name: 'What does orange mean?' }).click();
  await expect(dialog.getByRole('status')).toContainText('Checking project sources');
  await expect(dialog.getByRole('button', { name: 'Stop', exact: true })).toBeVisible();
  await page.getByLabel('Right image', { exact: true }).selectOption('20241108');
  await expect(dialog).toContainText('8 Nov 2024');
  await expect(dialog).toContainText('no water-area analysis for this pair');
  await expect(dialog.getByRole('article', { name: 'Your question' })).toHaveCount(0);
  release();
  await responded;
  await expect(dialog.getByText('STALE ANSWER FROM AUGUST PAIR')).toHaveCount(0);
  await dialog.getByLabel('Ask about this map').fill('What can we say about November?');
  await dialog.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toBeVisible();
  expect(requests[1].context).toEqual({ left_id: '20240828', right_id: '20241108', view_mode: 'compare' });
  expect(requests[1].history).toEqual([]);
});

test('a request can be stopped without inventing a reply or retaining failed history', async ({ page }) => {
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/api/chat', async (route) => {
    await delayed;
    try { await route.fulfill({ json: answer }); } catch { /* The browser aborted it. */ }
  });
  const dialog = await openChat(page);
  await dialog.getByRole('button', { name: 'Where is Kalari Abdu?' }).click();
  await expect(dialog.getByRole('status')).toBeVisible();
  await dialog.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('Request stopped');
  await expect(dialog.getByLabel('Ask about this map')).toHaveValue('Where is Kalari Abdu?');
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toHaveCount(0);
  release();
});

test('chat remains within the mobile viewport and closes back to the map', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/chat', (route) => route.fulfill({ json: answer }));
  const dialog = await openChat(page);
  const box = (await dialog.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(844);
  await dialog.getByRole('button', { name: 'What does orange mean?' }).click();
  await expect(dialog.getByRole('article', { name: 'Assistant answer' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await dialog.getByRole('button', { name: 'Close assistant' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByTestId('comparison-map')).toBeVisible();
});
