import threading
import logging
from typing import Dict, Any, Optional, Tuple

from task_store import TaskStore, TaskStatus

logger = logging.getLogger("BackgroundProcessor")


class BackgroundProcessor:
    """Handles deadline-based background processing of queries."""

    def __init__(self, notion_service, ai_handler, calendar_service,
                 intent_router, task_store: TaskStore,
                 areas: list, projects: list):
        self.notion = notion_service
        self.ai = ai_handler
        self.calendar = calendar_service
        self.router = intent_router
        self.store = task_store
        self.areas = areas
        self.projects = projects

    def process_with_deadline(self, query: str, deadline: float = 6.0) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Process a query with a deadline.

        Returns:
            (result, completed_in_time): Tuple with the result dict and whether it completed before deadline
        """
        task_id = self.store.create_task(query)
        completion_event = threading.Event()
        result_holder = {"result": None}

        # Start background thread
        thread = threading.Thread(
            target=self._process_full,
            args=(task_id, query, result_holder, completion_event),
            daemon=True
        )
        thread.start()

        # Wait for completion or deadline
        completed_in_time = completion_event.wait(timeout=deadline)

        if completed_in_time:
            return result_holder.get("result"), True
        else:
            # Background continues running
            return None, False

    def _process_full(self, task_id: str, query: str,
                      result_holder: Dict, completion_event: threading.Event):
        """Full processing logic (runs in background thread)."""
        self.store.update_task(task_id, TaskStatus.PROCESSING)

        try:
            # Step 1: Route the query (AI-based)
            domain = self.router.classify(query)
            logger.info(f"[{task_id}] Domain: {domain}")

            # Step 2: Fetch context and process
            result = self._handle_domain(query, domain)
            logger.info(f"[{task_id}] AI result: intent={result.get('intent')}")

            # Step 3: Execute actions
            response_text = self._execute_actions(domain, result)

            # Step 4: Store result
            self.store.update_task(
                task_id,
                TaskStatus.COMPLETED,
                result=response_text
            )

            # Update result holder for deadline wait
            result_holder["result"] = result
            result_holder["result"]["response"] = response_text

            logger.info(f"[{task_id}] Completed: {response_text[:50]}...")

        except Exception as e:
            logger.error(f"[{task_id}] Error: {e}")
            error_msg = f"Hubo un error procesando tu solicitud: {str(e)}"
            self.store.update_task(
                task_id,
                TaskStatus.FAILED,
                error=str(e),
                result=error_msg
            )
            result_holder["result"] = {
                "intent": "error",
                "response": error_msg
            }

        finally:
            # Signal completion (even on error)
            completion_event.set()

    def _handle_domain(self, query: str, domain: str) -> Dict[str, Any]:
        """Handle domain-specific processing."""
        if domain == "tasks":
            tasks = self.notion.get_active_tasks()
            context = {
                "areas": self.areas,
                "projects": self.projects,
                "tasks": tasks
            }
            return self.ai.handle_tasks(query, context)

        elif domain == "contacts":
            contacts = self.notion.get_contacts()

            # Enrich relevant contacts with page content
            query_low = query.lower()
            for contact in contacts:
                is_relevant = (
                    contact.get("favorite") or
                    contact.get("groups") == "Family" or
                    any(word in contact["name"].lower()
                        for word in query_low.split() if len(word) > 3) or
                    (contact.get("notes") and any(
                        word in contact["notes"].lower()
                        for word in query_low.split() if len(word) > 3
                    ))
                )

                if is_relevant:
                    logger.info(f"Fetching page content for: {contact['name']}")
                    contact["pageContent"] = self.notion.get_page_content(contact["id"])

            context = {"contacts": contacts}
            return self.ai.handle_contacts(query, context)

        else:  # general
            return self.ai.handle_general(query)

    def _execute_actions(self, domain: str, result: Dict[str, Any]) -> str:
        """Execute Notion/Calendar actions based on AI result."""
        intent = result.get("intent")
        response_text = result.get("response", "Procesado.")

        try:
            if domain == "tasks":
                if intent == "create":
                    task_data = result.get("task")
                    if task_data:
                        created_page = self.notion.add_task(task_data)
                        logger.info("Task created successfully.")

                        # Check for Calendar Sync
                        if task_data.get("createCalendarEvent") and task_data.get("dueDateTime"):
                            logger.info("Creating Google Calendar Event...")
                            event_id = self.calendar.create_event(
                                summary=task_data["name"],
                                start_time=task_data["dueDateTime"]
                            )

                            if event_id:
                                self.notion.update_task(created_page["id"], {"googleEventId": event_id})
                                logger.info(f"Synced with Calendar. Event ID: {event_id}")

                elif intent == "edit":
                    task_id = result.get("id")
                    updates = result.get("updates")
                    if task_id and updates:
                        # Fetch tasks for calendar sync check
                        tasks = self.notion.get_active_tasks()
                        self.notion.update_task(task_id, updates)
                        logger.info(f"Task {task_id} updated.")

                        # Check for Calendar Sync
                        if "dueDateTime" in updates or "dueDate" in updates or "name" in updates:
                            task_to_edit = next((t for t in tasks if t["id"] == task_id), None)
                            if task_to_edit and task_to_edit.get("googleEventId"):
                                logger.info(f"Updating Calendar Event {task_to_edit['googleEventId']}...")

                                calendar_updates = {}
                                if "dueDateTime" in updates:
                                    calendar_updates["dueDate"] = updates["dueDateTime"]
                                elif "dueDate" in updates:
                                    calendar_updates["dueDate"] = updates["dueDate"]
                                if "name" in updates:
                                    calendar_updates["name"] = updates["name"]

                                if calendar_updates:
                                    self.calendar.update_event(
                                        task_to_edit["googleEventId"],
                                        calendar_updates
                                    )

                        elif updates.get("done"):
                            task_to_edit = next((t for t in tasks if t["id"] == task_id), None)
                            if task_to_edit and task_to_edit.get("googleEventId"):
                                logger.info(f"Removing Calendar Event for completed task...")
                                if self.calendar.delete_event(task_to_edit["googleEventId"]):
                                    self.notion.update_task(task_id, {"googleEventId": ""})
                                    logger.info("Event removed.")

                elif intent == "delete":
                    task_id = result.get("id")
                    if task_id:
                        self.notion.archive_task(task_id)
                        logger.info(f"Task {task_id} archived.")

            elif domain == "contacts":
                if intent == "create":
                    contact_data = result.get("contact")
                    if contact_data:
                        self.notion.add_contact(contact_data)
                        logger.info("Contact created successfully.")

                elif intent == "edit":
                    contact_id = result.get("id")
                    updates = result.get("updates")
                    if contact_id and updates:
                        self.notion.update_contact(contact_id, updates)
                        logger.info(f"Contact {contact_id} updated.")

                elif intent == "delete":
                    contact_id = result.get("id")
                    if contact_id:
                        self.notion.archive_contact(contact_id)
                        logger.info(f"Contact {contact_id} archived.")

        except Exception as e:
            logger.error(f"Error executing action: {e}")
            response_text = f"Entendido, pero hubo un error ejecutando la acción: {str(e)}"

        return response_text
