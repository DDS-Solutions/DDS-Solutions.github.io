const { test, expect } = require('@playwright/test');

const PUBLIC_PAGES = [
    '/',
    '/3d-printer-monitor.html',
    '/accessories.html',
    '/air-gapped-security.html',
    '/baby-monitor.html',
    '/front-door-cam.html',
    '/garage-security.html',
    '/home-lab-monitor.html',
    '/laser-cnc-monitor.html',
    '/pet-monitor.html',
    '/privacy.html',
    '/rv-camper-security.html',
    '/terms.html',
    '/whats-new.html',
    '/wildlife-monitor.html',
];

test('every public page exposes one main landmark and a skip link', async ({ page }) => {
    for (const path of PUBLIC_PAGES) {
        await page.goto(path);
        await expect(page.locator('main#main-content')).toHaveCount(1);
        await expect(page.locator('.skip-link')).toHaveAttribute('href', '#main-content');
    }
});

test('homepage reveals content and exposes accessible carousel state', async ({ page }) => {
    await page.goto('/');

    const firstReveal = page.locator('.reveal').first();
    await firstReveal.scrollIntoViewIfNeeded();
    await expect(firstReveal).toHaveClass(/revealed/);

    const carousel = page.getByRole('region', { name: 'Application screenshots' });
    await expect(carousel).toHaveAttribute('tabindex', '0');

    const dots = page.locator('.carousel-dot');
    await expect(dots).toHaveCount(17);
    await expect(dots.first()).toHaveAttribute('aria-current', 'true');

    await dots.nth(5).click();
    await expect(dots.nth(5)).toHaveAttribute('aria-current', 'true');
    await expect(dots.first()).not.toHaveAttribute('aria-current', 'true');
});

test('modal restores focus and body overflow state', async ({ page }) => {
    await page.goto('/');

    const trigger = page.locator('#openFeatureModalBtn');
    const modal = page.locator('#featureModal');
    const originalOverflow = await page.locator('body').evaluate((body) => ({
        inlineY: body.style.overflowY,
        computedX: getComputedStyle(body).overflowX,
    }));

    await trigger.click();
    await expect(modal).toBeVisible();
    await expect(modal).toHaveAttribute('aria-hidden', 'false');
    await expect(page.locator('body')).toHaveCSS('overflow-y', 'hidden');

    await page.locator('#closeFeatureModalBtn').click();
    await expect(modal).toBeHidden();
    await expect(modal).toHaveAttribute('aria-hidden', 'true');
    await expect(trigger).toBeFocused();

    const restoredOverflow = await page.locator('body').evaluate((body) => ({
        inlineY: body.style.overflowY,
        computedX: getComputedStyle(body).overflowX,
    }));
    expect(restoredOverflow).toEqual(originalOverflow);
});

test('paid product messaging is consistent on the pet monitor page', async ({ page }) => {
    await page.goto('/pet-monitor.html');

    await expect(page.locator('body')).not.toContainText('Free pet monitor app');
    await expect(page.getByRole('link', { name: 'Get the App — One-Time Purchase' })).toBeVisible();
});
