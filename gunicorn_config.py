"""Gunicorn configuration for production deployment."""
import multiprocessing
import os

# Server socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:" + os.getenv("PORT", "5000"))
backlog = 2048

# Worker processes
# On Render free tier (512 MB RAM), keep workers=1.
# pandas + numpy + Flask fully loaded = ~250-350 MB per worker.
# Multiple workers will exceed the memory limit.
workers = int(os.getenv("GUNICORN_WORKERS", "1"))
worker_class = "gthread"   # Thread-based: cheaper than forking new processes
threads = int(os.getenv("GUNICORN_THREADS", "2"))  # 2 threads handles concurrent requests
worker_connections = 1000
timeout = 60  # Longer timeout since data fetching can be slow
keepalive = 2

# Process naming
proc_name = "alpaca_trader"

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Server mechanics
daemon = False
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if using HTTPS directly with Gunicorn)
# keyfile = "/path/to/key.pem"
# certfile = "/path/to/cert.pem"

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    print("Starting Alpaca Trader Dashboard...")


def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    print("Reloading workers...")


def when_ready(server):
    """Called just after the server is started."""
    print(f"Server is ready. Workers: {workers}")


def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    print(f"Worker spawned (pid: {worker.pid})")


def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    print(f"Worker {worker.pid} interrupted")


def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    print(f"Worker {worker.pid} aborted")
