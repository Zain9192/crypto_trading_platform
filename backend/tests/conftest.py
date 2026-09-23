import os

# Unit/integration suites inject controlled rate counters. The real Redis Lua
# path is exercised separately in the infrastructure suite.
os.environ.setdefault('RATE_LIMIT_ENABLED','false')
os.environ.setdefault('APP_ENV','test')
os.environ.setdefault('JWT_SECRET_KEY','test-only-secret-key-that-is-at-least-32-characters-long')
os.environ.setdefault('AUTH_DATA_ENCRYPTION_KEY','65ujGo4u-rd5tR5SJEB0mvwCv4DZIuk6S7jgpQ8xOEc=')
