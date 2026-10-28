"""Gunicorn settings for production (see Dockerfile)."""

import os

bind = "0.0.0.0:8000"

# Requests mostly wait on the LLM API, so threads give concurrency cheaply; each worker
# process holds pandas and a dataset in memory, so keep the process count small.
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))

# An LLM preview can take a while (generation plus one self-correction retry).
timeout = int(os.getenv("GUNICORN_TIMEOUT", "150"))
graceful_timeout = 30

accesslog = "-"
errorlog = "-"
