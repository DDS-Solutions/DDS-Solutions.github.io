const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
    testDir: './tests',
    timeout: 30_000,
    expect: {
        timeout: 7_500,
    },
    fullyParallel: false,
    forbidOnly: Boolean(process.env.CI),
    retries: process.env.CI ? 1 : 0,
    reporter: process.env.CI ? 'github' : 'list',
    use: {
        baseURL: 'http://127.0.0.1:4173',
        browserName: 'chromium',
        channel: process.env.CI ? undefined : 'chrome',
        trace: 'retain-on-failure',
    },
    webServer: {
        command: 'python -m http.server 4173 --bind 127.0.0.1',
        port: 4173,
        reuseExistingServer: !process.env.CI,
        timeout: 15_000,
    },
});
