import os
from notion_client import Client
import httpx
from typing import List, Dict, Any, Optional
import json

class NotionService:
    def __init__(self):
        self.api_key = os.getenv("NOTION_API_KEY")
        self.tasks_db_id = os.getenv("NOTION_TASKS_DATABASE_ID")
        self.areas_db_id = os.getenv("NOTION_AREAS_DATABASE_ID")
        self.projects_db_id = os.getenv("NOTION_PROJECTS_DATABASE_ID")

        if not self.api_key:
            raise ValueError("NOTION_API_KEY is not set")
        
        self.client = Client(auth=self.api_key)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }

    def get_areas(self) -> List[Dict[str, str]]:
        """Fetch all areas to build context."""
        if not self.areas_db_id:
            return []
        
        results = []
        has_more = True
        next_cursor = None

        while has_more:
            response = httpx.post(
                f"https://api.notion.com/v1/databases/{self.areas_db_id}/query",
                headers=self.headers,
                json={"start_cursor": next_cursor} if next_cursor else {},
                timeout=30.0
            ).json()
            for page in response["results"]:
                name_props = page["properties"].get("Name", {}).get("title", [])
                name = name_props[0]["text"]["content"] if name_props else "Untitled"
                results.append({"id": page["id"], "name": name})
            
            has_more = response["has_more"]
            next_cursor = response["next_cursor"]
            
        return results

    def get_projects(self) -> List[Dict[str, str]]:
        """Fetch active projects to build context."""
        if not self.projects_db_id:
            return []
            
        # You might want to filter only active projects here in the future
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{self.projects_db_id}/query",
            headers=self.headers,
            json={},
            timeout=30.0
        ).json()
        results = []
        for page in response["results"]:
            name_props = page["properties"].get("Name", {}).get("title", [])
            name = name_props[0]["text"]["content"] if name_props else "Untitled"
            results.append({"id": page["id"], "name": name})
        return results

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Fetch tasks that are not done."""
        # Querying for tasks where 'Done' checkbox is False OR Status is not Done
        # Adjust filter based on actual DB schema. Assuming 'Done' checkbox for now based on CLAUDE.md 'done' update.
        response = httpx.post(
            f"https://api.notion.com/v1/databases/{self.tasks_db_id}/query",
            headers=self.headers,
            json={
                "filter": {
                    "property": "Status",
                    "status": {
                        "does_not_equal": "Done"
                    }
                }
            },
            timeout=30.0
        ).json()
        
        tasks = []
        for page in response["results"]:
            props = page["properties"]
            name_parts = props.get("Task name", {}).get("title", [])
            name = name_parts[0]["text"]["content"] if name_parts else "Untitled"
            
            # Get event ID if exists
            event_id_parts = props.get("Google Event ID", {}).get("rich_text", [])
            google_event_id = event_id_parts[0]["text"]["content"] if event_id_parts else None

            tasks.append({
                "id": page["id"],
                "name": name,
                "url": page["url"],
                "googleEventId": google_event_id
            })
        return tasks

    def add_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task in Notion."""
        properties = {
            "Task name": {"title": [{"text": {"content": task_data["name"]}}]}
        }

        if task_data.get("dueDate"):
            properties["Due date"] = {"date": {"start": task_data["dueDate"]}}
        
        if task_data.get("dueDateTime"):
             properties["Due date"] = {"date": {"start": task_data["dueDateTime"]}}

        if task_data.get("priority"):
             properties["Priority"] = {"select": {"name": task_data["priority"]}}
             
        if task_data.get("urgent"):
             properties["Urgent"] = {"checkbox": task_data["urgent"]}
             
        if task_data.get("important"):
             properties["Important"] = {"checkbox": task_data["important"]}
             
        if task_data.get("areaId"):
            properties["Area"] = {"relation": [{"id": task_data["areaId"]}]}
            
        if task_data.get("projectId"):
            properties["Project"] = {"relation": [{"id": task_data["projectId"]}]}

        # Handling Recurring props
        if task_data.get("repeatCycle") and task_data.get("repeatEvery"):
             # Assuming these are Select and Number properties
             properties["Repeat cycle"] = {"select": {"name": task_data["repeatCycle"]}}
             properties["Repeat every"] = {"number": task_data["repeatEvery"]}

        if task_data.get("googleEventId"):
             properties["Google Event ID"] = {"rich_text": [{"text": {"content": task_data["googleEventId"]}}]}

        return self.client.pages.create(
            parent={"database_id": self.tasks_db_id},
            properties=properties
        )

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        properties = {}
        
        if "name" in updates:
            properties["Task name"] = {"title": [{"text": {"content": updates["name"]}}]}
            
        if "dueDate" in updates:
            properties["Due date"] = {"date": {"start": updates["dueDate"]}}

        if "dueDateTime" in updates:
            properties["Due date"] = {"date": {"start": updates["dueDateTime"]}}
            
        if "done" in updates:
            new_status = "Done" if updates["done"] else "To do"
            properties["Status"] = {"status": {"name": new_status}}
            
        if "priority" in updates:
            properties["Priority"] = {"select": {"name": updates["priority"]}}

        if "urgent" in updates:
            properties["Urgent"] = {"checkbox": updates["urgent"]}
            
        if "important" in updates:
            properties["Important"] = {"checkbox": updates["important"]}

        if "googleEventId" in updates:
             properties["Google Event ID"] = {"rich_text": [{"text": {"content": updates["googleEventId"]}}]}

        return self.client.pages.update(page_id=task_id, properties=properties)

    def archive_task(self, task_id: str) -> Dict[str, Any]:
        return self.client.pages.update(page_id=task_id, archived=True)
