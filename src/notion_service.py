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
        self.contacts_db_id = os.getenv("NOTION_CONTACTS_DATABASE_ID")

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

            # Extract due date
            due_date_obj = props.get("Due date", {}).get("date")
            due_date = due_date_obj.get("start") if due_date_obj else None
            
            # Extract priority
            priority_obj = props.get("Priority", {}).get("select")
            priority = priority_obj.get("name") if priority_obj else None
            
            # Extract urgent and important flags
            urgent = props.get("Urgent", {}).get("checkbox", False)
            important = props.get("Important", {}).get("checkbox", False)

            tasks.append({
                "id": page["id"],
                "name": name,
                "url": page["url"],
                "googleEventId": google_event_id,
                "dueDate": due_date,
                "priority": priority,
                "urgent": urgent,
                "important": important
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

    def get_contacts(self) -> List[Dict[str, Any]]:
        """Fetch all contacts with their relevant properties."""
        if not self.contacts_db_id:
            return []
        
        results = []
        has_more = True
        next_cursor = None

        while has_more:
            response = httpx.post(
                f"https://api.notion.com/v1/databases/{self.contacts_db_id}/query",
                headers=self.headers,
                json={"start_cursor": next_cursor} if next_cursor else {},
                timeout=30.0
            ).json()
            
            for page in response.get("results", []):
                props = page["properties"]
                
                # Name (title)
                name_parts = props.get("Name", {}).get("title", [])
                name = name_parts[0]["text"]["content"] if name_parts else "Untitled"
                
                # Company (rich_text)
                company_parts = props.get("Company", {}).get("rich_text", [])
                company = company_parts[0]["text"]["content"] if company_parts else None
                
                # Notes (rich_text)
                notes_parts = props.get("Notes", {}).get("rich_text", [])
                notes = notes_parts[0]["text"]["content"] if notes_parts else None
                
                # Email
                email = props.get("Email", {}).get("email")
                
                # Address (rich_text)
                address_parts = props.get("Address", {}).get("rich_text", [])
                address = address_parts[0]["text"]["content"] if address_parts else None
                
                # Social media (url)
                social_media = props.get("Social media", {}).get("url")
                
                # Birthday (date)
                birthday_obj = props.get("Birthday", {}).get("date")
                birthday = birthday_obj.get("start") if birthday_obj else None
                
                # Groups (select)
                groups_obj = props.get("Groups", {}).get("select")
                groups = groups_obj.get("name") if groups_obj else None
                
                # Favorite (checkbox)
                favorite = props.get("Favorite", {}).get("checkbox", False)
                
                # Age (formula - number result)
                age_obj = props.get("Age", {}).get("formula", {})
                age = age_obj.get("number") if age_obj.get("type") == "number" else None
                
                # Days until birthday (formula - number result)
                days_until_obj = props.get("Days until birthday", {}).get("formula", {})
                days_until_birthday = days_until_obj.get("number") if days_until_obj.get("type") == "number" else None
                
                # Next birthday (formula - string result)
                next_birthday_obj = props.get("Next birthday", {}).get("formula", {})
                next_birthday = next_birthday_obj.get("string") if next_birthday_obj.get("type") == "string" else None
                
                # Contact due? (formula - string result)
                contact_due_obj = props.get("Contact due?", {}).get("formula", {})
                contact_due = contact_due_obj.get("string") if contact_due_obj.get("type") == "string" else None
                
                # Last interaction (date)
                last_interaction_obj = props.get("Last interaction", {}).get("date")
                last_interaction = last_interaction_obj.get("start") if last_interaction_obj else None
                
                results.append({
                    "id": page["id"],
                    "name": name,
                    "company": company,
                    "notes": notes,
                    "email": email,
                    "address": address,
                    "socialMedia": social_media,
                    "birthday": birthday,
                    "groups": groups,
                    "favorite": favorite,
                    "age": age,
                    "daysUntilBirthday": days_until_birthday,
                    "nextBirthday": next_birthday,
                    "contactDue": contact_due,
                    "lastInteraction": last_interaction
                })
            
            has_more = response.get("has_more", False)
            next_cursor = response.get("next_cursor")
            
        return results

    def get_page_content(self, page_id: str) -> str:
        """Fetch the text content (blocks) inside a page."""
        content_parts = []
        has_more = True
        next_cursor = None
        
        while has_more:
            url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            params = {"start_cursor": next_cursor} if next_cursor else {}
            
            response = httpx.get(
                url,
                headers=self.headers,
                params=params,
                timeout=30.0
            ).json()
            
            for block in response.get("results", []):
                block_type = block.get("type")
                
                # Extract text from common block types
                if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                                  "bulleted_list_item", "numbered_list_item", "quote", 
                                  "callout", "toggle"]:
                    rich_text = block.get(block_type, {}).get("rich_text", [])
                    text = "".join([t.get("plain_text", "") for t in rich_text])
                    if text.strip():
                        content_parts.append(text.strip())
                        
                # Handle to-do items
                elif block_type == "to_do":
                    rich_text = block.get("to_do", {}).get("rich_text", [])
                    text = "".join([t.get("plain_text", "") for t in rich_text])
                    checked = block.get("to_do", {}).get("checked", False)
                    if text.strip():
                        prefix = "[x]" if checked else "[ ]"
                        content_parts.append(f"{prefix} {text.strip()}")
            
            has_more = response.get("has_more", False)
            next_cursor = response.get("next_cursor")
        
        return "\n".join(content_parts)

    def add_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new contact in Notion."""
        properties = {
            "Name": {"title": [{"text": {"content": contact_data["name"]}}]}
        }

        if contact_data.get("email"):
            properties["Email"] = {"email": contact_data["email"]}
        
        if contact_data.get("company"):
            properties["Company"] = {"rich_text": [{"text": {"content": contact_data["company"]}}]}
        
        if contact_data.get("address"):
            properties["Address"] = {"rich_text": [{"text": {"content": contact_data["address"]}}]}
        
        if contact_data.get("notes"):
            properties["Notes"] = {"rich_text": [{"text": {"content": contact_data["notes"]}}]}
        
        if contact_data.get("socialMedia"):
            properties["Social media"] = {"url": contact_data["socialMedia"]}
        
        if contact_data.get("birthday"):
            properties["Birthday"] = {"date": {"start": contact_data["birthday"]}}
        
        if contact_data.get("groups"):
            properties["Groups"] = {"select": {"name": contact_data["groups"]}}
        
        if contact_data.get("favorite"):
            properties["Favorite"] = {"checkbox": contact_data["favorite"]}
        
        if contact_data.get("mustContactEvery"):
            properties["Must contact every (days)"] = {"number": contact_data["mustContactEvery"]}

        return self.client.pages.create(
            parent={"database_id": self.contacts_db_id},
            properties=properties
        )

    def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing contact in Notion."""
        properties = {}
        
        if "name" in updates:
            properties["Name"] = {"title": [{"text": {"content": updates["name"]}}]}
        
        if "email" in updates:
            properties["Email"] = {"email": updates["email"]}
        
        if "company" in updates:
            properties["Company"] = {"rich_text": [{"text": {"content": updates["company"]}}]}
        
        if "address" in updates:
            properties["Address"] = {"rich_text": [{"text": {"content": updates["address"]}}]}
        
        if "notes" in updates:
            properties["Notes"] = {"rich_text": [{"text": {"content": updates["notes"]}}]}
        
        if "socialMedia" in updates:
            properties["Social media"] = {"url": updates["socialMedia"]}
        
        if "birthday" in updates:
            properties["Birthday"] = {"date": {"start": updates["birthday"]}}
        
        if "groups" in updates:
            properties["Groups"] = {"select": {"name": updates["groups"]}}
        
        if "favorite" in updates:
            properties["Favorite"] = {"checkbox": updates["favorite"]}
        
        if "mustContactEvery" in updates:
            properties["Must contact every (days)"] = {"number": updates["mustContactEvery"]}
        
        if "lastInteraction" in updates:
            properties["Last interaction"] = {"date": {"start": updates["lastInteraction"]}}

        return self.client.pages.update(page_id=contact_id, properties=properties)

    def archive_contact(self, contact_id: str) -> Dict[str, Any]:
        """Archive (delete) a contact."""
        return self.client.pages.update(page_id=contact_id, archived=True)
