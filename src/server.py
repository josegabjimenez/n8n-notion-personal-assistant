import os
import socket
import sys
import json
import logging
import threading
from dotenv import load_dotenv
from notion_service import NotionService
from ai_handler import AIHandler
from calendar_service import CalendarService
from intent_router import IntentRouter
from task_store import TaskStore
from background_processor import BackgroundProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("NotionAgent")

# Status query keywords for fast detection (no AI call needed)
STATUS_KEYWORDS = [
    "qué pasó", "que paso", "terminaste", "resultado",
    "qué hiciste", "que hiciste", "cuéntame", "cuentame",
    "ya quedó", "ya quedo", "listo"
]


def is_status_query(query: str) -> bool:
    """Fast check if this is a status query."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in STATUS_KEYWORDS)


def handle_connection(conn, ai, task_store, bg_processor, deadline_seconds=6.0):
    """Handle a single connection with deadline-based processing."""
    try:
        # Read Query
        data = conn.recv(4096)
        if not data:
            return

        query = data.decode("utf-8").strip()
        logger.info(f"Received query: {query}")

        # Fast path: Status query (no background processing needed)
        if is_status_query(query):
            logger.info("Detected status query - fast path")
            result = ai.handle_status(query, task_store)
            response_text = result.get("response", "No tengo información disponible.")
            conn.sendall(response_text.encode("utf-8"))
            return

        # Normal path: Deadline-based processing
        logger.info(f"Starting deadline-based processing (deadline={deadline_seconds}s)")
        result, completed_in_time = bg_processor.process_with_deadline(query, deadline_seconds)

        if completed_in_time:
            # Task completed within deadline - return actual response
            response_text = result.get("response", "Procesado.")
            logger.info(f"Completed in time: {response_text[:50]}...")
        else:
            # Deadline exceeded - return acknowledgment, continue in background
            response_text = "Procesando tu solicitud, pregúntame en unos segundos qué pasó."
            logger.info("Deadline exceeded - returning acknowledgment")

        conn.sendall(response_text.encode("utf-8"))

    except Exception as e:
        logger.error(f"Error handling connection: {e}")
        conn.sendall(b"Error interno del servidor.")
    finally:
        conn.close()


def main():
    # Load Environment
    load_dotenv()
    socket_path = os.getenv("SOCKET_PATH", "/tmp/notion_agent.sock")
    deadline_seconds = float(os.getenv("DEADLINE_SECONDS", "6.0"))

    # Initialize Services
    try:
        logger.info("Initializing Notion Service...")
        notion = NotionService()

        logger.info("Initializing AI Handler...")
        ai = AIHandler()

        logger.info("Initializing Intent Router...")
        router = IntentRouter()

        logger.info("Initializing Calendar Service...")
        calendar = CalendarService()

        logger.info("Initializing Task Store...")
        task_store = TaskStore(max_tasks=50, ttl_seconds=300)

        # Cache Static Context (Areas/Projects)
        logger.info("Fetching static context (Areas/Projects)...")
        areas = notion.get_areas()
        projects = notion.get_projects()
        logger.info(f"Loaded {len(areas)} areas and {len(projects)} projects.")

        logger.info("Initializing Background Processor...")
        bg_processor = BackgroundProcessor(
            notion_service=notion,
            ai_handler=ai,
            calendar_service=calendar,
            intent_router=router,
            task_store=task_store,
            areas=areas,
            projects=projects
        )

    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        sys.exit(1)

    # Setup Socket
    if os.path.exists(socket_path):
        os.remove(socket_path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(5)  # Increased backlog for concurrent requests

    # Ensure socket is accessible
    os.chmod(socket_path, 0o777)

    logger.info(f"Listening on {socket_path}...")
    logger.info(f"Deadline for responses: {deadline_seconds} seconds")

    try:
        while True:
            conn, _ = server.accept()
            # Handle each connection in a separate thread for concurrency
            thread = threading.Thread(
                target=handle_connection,
                args=(conn, ai, task_store, bg_processor, deadline_seconds),
                daemon=True
            )
            thread.start()

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.close()
        if os.path.exists(socket_path):
            os.remove(socket_path)


if __name__ == "__main__":
    main()
