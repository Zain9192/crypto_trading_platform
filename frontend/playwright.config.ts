import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir:'./e2e', workers:1, timeout:60000, retries:0,
  reporter:[['list'],['json',{outputFile:'test-results/e2e.json'}]],
  use:{baseURL:'http://127.0.0.1:5173',trace:'retain-on-failure'},
  webServer:[
    {command:'python -m uvicorn qa.server:app --host 127.0.0.1 --port 8000 --no-proxy-headers',cwd:'../backend',url:'http://127.0.0.1:8000/api/v1/health',timeout:120000,reuseExistingServer:!process.env.CI},
    {command:'npm run dev -- --host 127.0.0.1',url:'http://127.0.0.1:5173',timeout:60000,reuseExistingServer:!process.env.CI},
  ],
})
