"""
Worker entrypoint.

Usage (from the service root)::

    python -m arq app.worker.main.WorkerSettings

The ``ai-worker`` Docker service in docker-compose.yml uses exactly this
command.  arq discovers ``WorkerSettings`` via the dotted module path.
"""

from app.worker.tasks import WorkerSettings  # re-exported as the public name

__all__ = ["WorkerSettings"]
