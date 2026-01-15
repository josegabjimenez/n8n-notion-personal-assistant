import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, os.path.dirname(__file__))

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("HTTPServer")

# Thread pool for CPU-bound operations
executor = ThreadPoolExecutor(max_workers=4)

# Global instances (initialized in lifespan)
notion_service = None
ai_handler = None
intent_router = None
calendar_service = None
task_store = None
conversation_store = None
bg_processor = None


class QueryRequest(BaseModel):
    """Request model for query endpoint."""
    query: str
    timeout: float = 6.0
    session_id: Optional[str] = None  # For conversation memory within Alexa sessions


class QueryResponse(BaseModel):
    """Response model for query endpoint."""
    response: str
    status: str  # "completed" | "processing"
    task_id: Optional[str] = None


def is_status_query(query: str) -> bool:
    """Check if query is asking about background task status."""
    keywords = ["qué pasó", "que paso", "terminaste", "resultado", "listo", "ya quedó", "ya quedo"]
    query_lower = query.lower()
    return any(kw in query_lower for kw in keywords)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, cleanup on shutdown."""
    global notion_service, ai_handler, intent_router, calendar_service
    global task_store, conversation_store, bg_processor

    from notion_service import NotionService
    from ai_handler import AIHandler
    from intent_router import IntentRouter
    from calendar_service import CalendarService
    from task_store import TaskStore
    from conversation_store import ConversationStore
    from background_processor import BackgroundProcessor
    from ai_client import AIClient

    logger.info("Initializing services...")

    # Shared AI client (reused across components)
    ai_client = AIClient()

    notion_service = NotionService()
    ai_handler = AIHandler(ai_client=ai_client)
    intent_router = IntentRouter(ai_client=ai_client)
    calendar_service = CalendarService()
    task_store = TaskStore()
    conversation_store = ConversationStore()  # Session memory for multi-turn conversations

    # Cache static context at startup
    logger.info("Loading areas and projects...")
    areas = notion_service.get_areas()
    projects = notion_service.get_projects()
    logger.info(f"Loaded {len(areas)} areas and {len(projects)} projects")

    bg_processor = BackgroundProcessor(
        notion_service, ai_handler, calendar_service,
        intent_router, task_store, conversation_store, areas, projects
    )

    logger.info("Services initialized successfully")
    yield

    # Cleanup
    logger.info("Shutting down...")
    executor.shutdown(wait=False)


app = FastAPI(
    title="Notion Personal Agent",
    description="Personal assistant for Notion with Alexa integration",
    version="2.0.0",
    lifespan=lifespan
)


@app.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """
    Main endpoint for Alexa/n8n integration.

    Processes queries with a deadline-based approach:
    - If completed within timeout: returns actual response
    - If timeout exceeded: returns "processing" status and continues in background
    """
    query = request.query
    deadline = request.timeout

    logger.info(f"Received query: {query[:50]}... (timeout: {deadline}s)")

    # Fast path: Status queries
    if is_status_query(query):
        logger.info("Fast path: status query")
        result = ai_handler.handle_status(query, task_store)
        return QueryResponse(
            response=result.get("response", "No tengo información"),
            status="completed"
        )

    # Deadline-based processing using thread pool
    loop = asyncio.get_event_loop()
    session_id = request.session_id

    try:
        result, completed = await asyncio.wait_for(
            loop.run_in_executor(
                executor,
                lambda: bg_processor.process_with_deadline(query, deadline, session_id)
            ),
            timeout=deadline + 0.5  # Small buffer for executor overhead
        )

        if completed and result:
            logger.info(f"Query completed in time: {result.get('intent', 'unknown')}")
            return QueryResponse(
                response=result.get("response", "Procesado"),
                status="completed"
            )
        else:
            logger.info("Query exceeded deadline, continuing in background")
            return QueryResponse(
                response="Procesando tu solicitud, pregúntame en unos segundos qué pasó.",
                status="processing"
            )

    except asyncio.TimeoutError:
        logger.warning("Query timed out")
        return QueryResponse(
            response="Procesando tu solicitud, pregúntame en unos segundos qué pasó.",
            status="processing"
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return QueryResponse(
            response=f"Lo siento, hubo un error: {str(e)}",
            status="completed"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "notion-agent",
        "version": "2.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Notion Personal Agent",
        "version": "2.0.0",
        "endpoints": {
            "POST /query": "Main query endpoint",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HTTP_HOST", "0.0.0.0")
    port = int(os.getenv("HTTP_PORT", "8080"))

    logger.info(f"Starting HTTP server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
