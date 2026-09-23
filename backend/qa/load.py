"""Measure the Phase 10 HTTP concurrency target against the QA server."""
import asyncio
import json
import os
import statistics
import time

import aiohttp


async def main():
    base = os.getenv('QA_BASE_URL', 'http://127.0.0.1:8000')
    users = int(os.getenv('QA_CONCURRENCY', '500'))
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=users)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async def request(index):
            started = time.perf_counter()
            try:
                # The health endpoint avoids external providers and exercises the same ASGI stack.
                async with session.get(f'{base}/api/v1/health', headers={'X-QA-User': str(index)}) as response:
                    await response.read()
                    return response.status, 1000 * (time.perf_counter() - started)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return 0, 1000 * (time.perf_counter() - started)
        results = await asyncio.gather(*(request(i) for i in range(users)))
    latencies = sorted(duration for _, duration in results)
    statuses = {str(status): sum(code == status for code, _ in results) for status in sorted({r[0] for r in results})}
    summary = {'concurrency': users, 'statuses': statuses,
               'median_ms': round(statistics.median(latencies), 1),
               'p95_ms': round(latencies[int(.95 * (len(latencies) - 1))], 1),
               'max_ms': round(latencies[-1], 1)}
    print(json.dumps(summary, sort_keys=True))
    if any(status != 200 for status, _ in results):
        raise SystemExit('HTTP requests failed under concurrency')


if __name__ == '__main__':
    asyncio.run(main())
