import { chromium } from 'playwright';

async function capture() {
  console.log("Launching Chromium...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2
  });
  const page = await context.newPage();

  // 1. Capture Landing Page
  console.log("Navigating to Landing Page (http://127.0.0.1:5173/)...");
  await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
  await page.waitForTimeout(4000); // Ensure all images, modern CSS gradient cards, fonts & buttons render completely
  const landingPath = "/Users/snazalsingh/Downloads/MeetingSummarizer/ui_screenshot_landing.png";
  await page.screenshot({ path: landingPath, fullPage: false });
  console.log(`Captured Landing Page -> ${landingPath}`);

  // 2. Capture App Page
  console.log("Navigating to App Workspace (http://127.0.0.1:5173/app)...");
  await page.goto("http://127.0.0.1:5173/app", { waitUntil: "networkidle" });
  await page.waitForTimeout(4000); // Ensure tabs, upload cards & icons render fully
  
  // Fill sample text into Paste Text tab to showcase a rich filled workspace
  try {
    const pasteTab = page.locator("button:has-text('Paste Text'), [role='tab']:has-text('Paste')").first();
    if (await pasteTab.isVisible()) {
      await pasteTab.click();
      await page.waitForTimeout(1000);
      const textarea = page.locator("textarea").first();
      if (await textarea.isVisible()) {
        await textarea.fill("[00:00.0] Alice: Welcome everyone. Let's review the Q3 product roadmap and server budget.\n[00:04.2] Bob: Thanks Alice. Server hosting costs grew by 15% last month. I propose migrating our database to AWS.\n[00:10.5] Charlie: I agree with the migration proposal. I'll finalize the pricing research by Friday.\n[00:15.0] Alice: Excellent, let's schedule the migration rollout for next sprint.");
      }
    }
  } catch (e) {
    console.log("Note during workspace text fill:", e.message);
  }

  await page.waitForTimeout(2000);
  const appPath = "/Users/snazalsingh/Downloads/MeetingSummarizer/ui_screenshot_app.png";
  await page.screenshot({ path: appPath, fullPage: false });
  console.log(`Captured App Workspace -> ${appPath}`);

  await browser.close();
  console.log("Screenshot capture complete!");
}

capture().catch(err => {
  console.error("Capture error:", err);
  process.exit(1);
});
