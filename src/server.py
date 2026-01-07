import os
import socket
import sys
import json
import logging
from dotenv import load_dotenv
from notion_service import NotionService
from ai_handler import AIHandler
from calendar_service import CalendarService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("NotionAgent")

def main():
    # Load Environment
    load_dotenv()
    socket_path = os.getenv("SOCKET_PATH", "/tmp/notion_agent.sock")

    # Initialize Services
    try:
        logger.info("Initializing Notion Service...")
        notion = NotionService()
        
        logger.info("Initializing AI Handler...")
        ai = AIHandler()

        logger.info("Initializing Calendar Service...")
        calendar = CalendarService()
        
        # Cache Context (Areas/Projects)
        logger.info("Fetching static context (Areas/Projects)...")
        areas = notion.get_areas()
        projects = notion.get_projects()
        logger.info(f"Loaded {len(areas)} areas and {len(projects)} projects.")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        sys.exit(1)

    # Setup Socket
    if os.path.exists(socket_path):
        os.remove(socket_path)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(1)
    
    # Ensure socket is accessible
    os.chmod(socket_path, 0o777)
    
    logger.info(f"Listening on {socket_path}...")

    try:
        while True:
            conn, _ = server.accept()
            try:
                # Read Query
                data = conn.recv(4096)
                if not data:
                    break
                
                query = data.decode("utf-8").strip()
                logger.info(f"Received query: {query}")
                
                # Fetch Dynamic Context (Active Tasks)
                # We fetch this every time to ensure we have the latest state for Edit/Delete
                tasks = notion.get_active_tasks()
                
                context = {
                    "areas": areas,
                    "projects": projects,
                    "tasks": tasks
                }
                
                # Classify Intent
                result = ai.classify_intent(query, context)
                intent = result.get("intent")
                logger.info(f"Identified intent: {intent}")
                
                response_text = result.get("response", "Error processing request.")
                
                # Execute Action
                try:
                    if intent == "create":
                        task_data = result.get("task")
                        if task_data:
                            created_page = notion.add_task(task_data)
                            logger.info("Task created successfully.")

                            # Check for Calendar Sync
                            if task_data.get("createCalendarEvent") and task_data.get("dueDateTime"):
                                logger.info("Creating Google Calendar Event...")
                                event_id = calendar.create_event(
                                    summary=task_data["name"],
                                    start_time=task_data["dueDateTime"]
                                )
                                
                                if event_id:
                                    # Update Notion with Event ID
                                    notion.update_task(created_page["id"], {"googleEventId": event_id})
                                    logger.info(f"Synced with Calendar. Event ID: {event_id}")
                            
                    elif intent == "edit":
                        task_id = result.get("id")
                        updates = result.get("updates")
                        if task_id and updates:
                            notion.update_task(task_id, updates)
                            logger.info(f"Task {task_id} updated.")

                            # Check for Calendar Sync
                            # If checking for TIME updates to sync existing event:
                            if "dueDateTime" in updates or "name" in updates:
                                # Find event ID from context
                                task_to_edit = next((t for t in tasks if t["id"] == task_id), None)
                                if task_to_edit and task_to_edit.get("googleEventId"):
                                    logger.info(f"Updating Google Calendar Event {task_to_edit['googleEventId']}...")
                                    
                                    calendar_updates = {}
                                    if "dueDateTime" in updates:
                                        calendar_updates["dueDate"] = updates["dueDateTime"]
                                    if "name" in updates:
                                        calendar_updates["name"] = updates["name"]
                                    
                            
                            elif updates.get("done"):
                                # If task is completed, check if we need to remove calendar event
                                task_to_edit = next((t for t in tasks if t["id"] == task_id), None)
                                if task_to_edit and task_to_edit.get("googleEventId"):
                                     logger.info(f"Removing Google Calendar Event {task_to_edit['googleEventId']} for completed task...")
                                     if calendar.delete_event(task_to_edit["googleEventId"]):
                                          # Optional: Clear the ID from Notion or just leave it. 
                                          # Clearing it prevents future confusion if un-done, but maybe better to keep record?
                                          # Let's clear it to indicate no active sync.
                                          notion.update_task(task_id, {"googleEventId": ""})
                                          logger.info("Event removed.")
                            
                    elif intent == "delete":
                        task_id = result.get("id")
                        if task_id:
                            notion.archive_task(task_id)
                            logger.info(f"Task {task_id} archived.")
                            
                except Exception as e:
                    logger.error(f"Error executing Notion action: {e}")
                    response_text = f"Entendido, pero hubo un error ejecutando la acción en Notion: {str(e)}"

                # Send Response
                conn.sendall(response_text.encode("utf-8"))
                
            except Exception as e:
                logger.error(f"Error handling connection: {e}")
                conn.sendall(b"Error interno del servidor.")
            finally:
                conn.close()
                
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        server.close()
        if os.path.exists(socket_path):
            os.remove(socket_path)

if __name__ == "__main__":
    main()
