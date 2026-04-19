"""Application entry point."""
import logging

from waitress import serve

from app import create_app

logger = logging.getLogger(__name__)

app = create_app()

if __name__ == "__main__":
    logger.info("Starting server on port 8090")
    serve(app, host="0.0.0.0", port=8090)
