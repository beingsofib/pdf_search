"""Background PDF indexer with status tracking."""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
status = {
    'running': False,
    'last_run': None,
    'message': '',
    'error': None,
}


def run(db_path, pdf_dir):
    """Run the extractor in a background thread. Call from a daemon thread."""
    global status
    with _lock:
        if status['running']:
            return
        status['running'] = True
        status['error'] = None
        status['message'] = 'Starting...'

    def _on_progress(msg):
        status['message'] = msg

    try:
        from extractor import init_db, scan_directory
        init_db(db_path)
        scan_directory(pdf_dir, db_path, progress_callback=_on_progress,
                       use_threads=True)
        status['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
        status['message'] = ''
    except Exception as e:
        logger.exception("Indexer error")
        status['error'] = str(e)
        status['message'] = ''
    finally:
        status['running'] = False


def start_periodic(db_path, pdf_dir, interval=3600):
    """Run the indexer on startup, then every `interval` seconds. Blocking."""
    while True:
        run(db_path, pdf_dir)
        time.sleep(interval)
