# CLAUDE.md - Jose's Personal Assistant Architecture

## Overview

This is Jose's personal Notion assistant with an **intent-based routing architecture**. The system can manage tasks and query contact information from his "Second Brain" Notion workspace.

---

## Architecture

```
User Query → Intent Router → Domain-Specific Agent → Response
                   ↓
         [tasks | contacts | general]
                   ↓
         Fetch Domain Context
                   ↓
         Specialized AI Agent
                   ↓
         Execute Actions (if needed)
```

### Components

1. **Intent Router** (`prompts/ROUTER.md`)
   - Lightweight classifier that routes queries to: `tasks`, `contacts`, `status`, or `general`
   - Fast, cheap, single-word response

2. **Tasks Agent** (`prompts/TASKS_AGENT.md`)
   - Query, create, edit, delete tasks
   - Auto-categorizes by Area
   - Supports recurring tasks and calendar reminders

3. **Contacts Agent** (`prompts/CONTACTS_AGENT.md`)
   - Query contact information
   - Search by name, group, or relationship
   - Birthday and contact-due reminders

4. **General Agent** (`prompts/GENERAL_AGENT.md`)
   - Greetings and chitchat
   - Capability explanations

5. **Status Agent** (`prompts/STATUS_AGENT.md`)
   - Handles queries about background task results
   - AI-based smart matching for concurrent tasks
   - Returns results and marks tasks as consumed

---

## Async Response Architecture (Alexa Integration)

### Problem Solved
Alexa times out after ~8 seconds, but some operations (task creation with calendar sync) take 10-17 seconds.

### Solution: Deadline-Based Response Pattern
1. Requests are processed in background threads
2. Server waits up to 6 seconds for completion (configurable via `DEADLINE_SECONDS`)
3. If completed in time: returns actual response
4. If deadline exceeded: returns "Procesando, pregúntame qué pasó" and continues in background

### Status Query Flow
- User asks "¿Qué pasó?" to retrieve background task results
- AI-based smart matching picks the correct task from pending/completed list
- Once a result is returned, the task is marked "consumed" (won't appear again)

### Key Async Files
- `src/task_store.py` - Thread-safe in-memory store for background tasks
- `src/background_processor.py` - Handles deadline-based processing
- `prompts/STATUS_AGENT.md` - AI prompt for smart task matching

### Status Intent (Router)
The "status" domain handles queries about pending/completed tasks:
- "¿Qué pasó?" → status
- "¿Terminaste?" → status
- "¿Qué pasó con el contacto?" → status (with context for smart matching)

### Threading Model
- Each socket connection handled in a daemon thread
- Background processor uses `threading.Event` for deadline signaling
- TaskStore uses `threading.Lock` for thread-safe access

---

## Adding New Domains

To add a new domain (e.g., "notes", "calendar", "spotify"):

1. **Update Router**: Add new domain to `prompts/ROUTER.md` classification rules
2. **Create Agent Prompt**: Add `prompts/NEW_DOMAIN_AGENT.md`
3. **Add Context Method**: Add data fetching to `notion_service.py` if needed
4. **Add Handler**: Add `handle_new_domain()` to `ai_handler.py`
5. **Update Server**: Add routing case in `server.py`

---

## Configuration

Required environment variables:

```
NOTION_API_KEY=<integration token>
NOTION_TASKS_DATABASE_ID=<tasks db id>
NOTION_AREAS_DATABASE_ID=<areas db id>
NOTION_PROJECTS_DATABASE_ID=<projects db id>
NOTION_CONTACTS_DATABASE_ID=<contacts db id>
AI_CLI_COMMAND=claude -p --model claude-haiku-4-5-20251001
SOCKET_PATH=/tmp/notion_agent.sock
DEADLINE_SECONDS=6.0  # Optional: deadline for Alexa responses (default: 6.0)
```

---

## Response Rules (All Agents)

1. **Language**: Default Colombian Spanish, tuteo form
2. **Format**: Voice-optimized, no markdown/emojis in responses
3. **Output**: Always valid JSON
4. **Timezone**: Colombia (-05:00)

---

## File Structure

```
notion-personal-agent/
├── src/
│   ├── server.py              # Main socket server (deadline-based flow)
│   ├── client.py              # CLI client
│   ├── intent_router.py       # Query domain classifier
│   ├── ai_handler.py          # AI handlers per domain
│   ├── notion_service.py      # Notion API wrapper
│   ├── calendar_service.py    # Google Calendar integration
│   ├── task_store.py          # Thread-safe background task store
│   └── background_processor.py # Deadline-based async processing
├── prompts/
│   ├── ROUTER.md              # Intent classification
│   ├── TASKS_AGENT.md         # Task management
│   ├── CONTACTS_AGENT.md      # Contact queries
│   ├── GENERAL_AGENT.md       # Chitchat
│   └── STATUS_AGENT.md        # Background task status queries
└── CLAUDE.md                  # This file
```
