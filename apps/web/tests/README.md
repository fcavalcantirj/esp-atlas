# Browser regressions

From `apps/web`, run:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

The suite starts isolated fixture API and Next.js servers on ports 8766 and 4186.
It exercises desktop and touch-sized mobile viewports. Fixtures are explicitly
synthetic; no inference, hardware access, or production analytics is involved.
To use an installed Chrome instead, set `PLAYWRIGHT_CHANNEL=chrome`.

The tests check visible/focused answers, loading and retry behavior, stale-request
isolation, malformed payloads, the firmware reveal cap, complete API ordering in
all five sorts, hidden keyboard/accessibility content, and final-page focus.
They supplement real-catalog browser verification; they do not verify firmware
compatibility or replace backend sorting tests.
