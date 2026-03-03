# gunicorn configuration for running the Shiny app in production
import multiprocessing

workers = int((multiprocessing.cpu_count() * 2) + 1)
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
bind = "0.0.0.0:8000"
