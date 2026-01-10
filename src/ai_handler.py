import os
import json
import subprocess
import shlex
import datetime
from typing import Dict, Any

class AIHandler:
    def __init__(self):
        self.cli_command = os.getenv("AI_CLI_COMMAND", "claude")
        self.prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

    def _load_prompt(self, prompt_name: str) -> str:
        """Load a prompt file from the prompts directory."""
        prompt_path = os.path.join(self.prompts_dir, prompt_name)
        with open(prompt_path, "r") as f:
            return f.read()

    def _get_time_context(self) -> str:
        """Get current time context for Colombia timezone."""
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/Bogota")
        except ImportError:
            tz = datetime.timezone(datetime.timedelta(hours=-5))

        now = datetime.datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d %A")
        time_str = now.strftime("%H:%M:%S")
        
        return f"CURRENT DATE: {today_str}\nCURRENT TIME: {time_str} (Timezone: America/Bogota)\n"

    def _call_ai(self, full_prompt: str) -> Dict[str, Any]:
        """Execute AI CLI and parse JSON response."""
        cmd = shlex.split(self.cli_command)
        cmd.append(full_prompt)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            
            # Extract JSON from markdown code blocks if present
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                output = output.split("```")[1].strip()
                
            return json.loads(output)
            
        except subprocess.CalledProcessError as e:
            return {
                "intent": "query",
                "response": f"Lo siento, hubo un error al procesar tu solicitud. Error: {e.stderr}",
            }
        except json.JSONDecodeError:
            return {
                "intent": "query",
                "response": "Lo siento, la respuesta de la IA no fue válida. " + output[:100],
            }

    def handle_tasks(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle task-related queries using TASKS_AGENT prompt."""
        system_prompt = self._load_prompt("TASKS_AGENT.md")
        
        context_str = f"\n\n--- DYNAMIC CONTEXT ---\n"
        context_str += self._get_time_context()
        
        context_str += "\nAVAILABLE AREAS:\n"
        for area in context.get("areas", []):
            context_str += f"- {area['name']} (ID: {area['id']})\n"
            
        context_str += "\nAVAILABLE PROJECTS:\n"
        for proj in context.get("projects", []):
            context_str += f"- {proj['name']} (ID: {proj['id']})\n"
            
        context_str += "\nEXISTING TASKS (Recent/Active):\n"
        for task in context.get("tasks", []):
            task_line = f"- {task['name']} (ID: {task['id']})"
            
            if task.get('dueDate'):
                task_line += f" | Due: {task['dueDate']}"
            if task.get('priority'):
                task_line += f" | Priority: {task['priority']}"
            
            flags = []
            if task.get('urgent'):
                flags.append("Urgent")
            if task.get('important'):
                flags.append("Important")
            if flags:
                task_line += f" | Flags: {', '.join(flags)}"
            
            context_str += task_line + "\n"

        full_prompt = f"{system_prompt}\n{context_str}\n\nUSER INPUT: \"{query}\""
        return self._call_ai(full_prompt)

    def handle_contacts(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle contact-related queries using CONTACTS_AGENT prompt."""
        system_prompt = self._load_prompt("CONTACTS_AGENT.md")
        
        context_str = f"\n\n--- DYNAMIC CONTEXT ---\n"
        context_str += self._get_time_context()
        
        context_str += "\nCONTACTS:\n"
        for contact in context.get("contacts", []):
            contact_line = f"- {contact['name']} (ID: {contact['id']})"
            
            if contact.get('groups'):
                contact_line += f" | Group: {contact['groups']}"
            if contact.get('company'):
                contact_line += f" | Company: {contact['company']}"
            if contact.get('email'):
                contact_line += f" | Email: {contact['email']}"
            if contact.get('birthday'):
                contact_line += f" | Birthday: {contact['birthday']}"
            if contact.get('age') is not None:
                contact_line += f" | Age: {contact['age']}"
            if contact.get('daysUntilBirthday') is not None:
                contact_line += f" | Days until birthday: {contact['daysUntilBirthday']}"
            if contact.get('notes'):
                contact_line += f" | Notes: {contact['notes']}"
            if contact.get('favorite'):
                contact_line += " | ⭐ Favorite"
            if contact.get('contactDue'):
                contact_line += f" | Status: {contact['contactDue']}"
            if contact.get('pageContent'):
                contact_line += f" | Page Content: {contact['pageContent']}"
            
            context_str += contact_line + "\n"

        full_prompt = f"{system_prompt}\n{context_str}\n\nUSER INPUT: \"{query}\""
        return self._call_ai(full_prompt)

    def handle_general(self, query: str) -> Dict[str, Any]:
        """Handle general conversation using GENERAL_AGENT prompt."""
        system_prompt = self._load_prompt("GENERAL_AGENT.md")

        context_str = f"\n\n--- DYNAMIC CONTEXT ---\n"
        context_str += self._get_time_context()

        full_prompt = f"{system_prompt}\n{context_str}\n\nUSER INPUT: \"{query}\""
        return self._call_ai(full_prompt)

    def handle_status(self, query: str, task_store) -> Dict[str, Any]:
        """Handle status queries using STATUS_AGENT prompt with smart matching."""
        pending = task_store.get_pending_tasks()
        completed = task_store.get_recent_completed()

        # Fast path: No tasks at all
        if not pending and not completed:
            return {
                "intent": "status",
                "response": "No tengo tareas procesando. ¿En qué te puedo ayudar?"
            }

        # Fast path: Only pending tasks, no completed
        if pending and not completed:
            # Describe what's still processing
            task_descriptions = [t.query[:50] for t in pending[:3]]
            if len(pending) == 1:
                return {
                    "intent": "status",
                    "response": "Todavía estoy trabajando en eso. Dame unos segundos más."
                }
            else:
                return {
                    "intent": "status",
                    "response": f"Tengo {len(pending)} tareas procesando. Dame unos segundos más."
                }

        # Use AI to match query to the right completed task
        system_prompt = self._load_prompt("STATUS_AGENT.md")

        context_str = "\n\n--- DYNAMIC CONTEXT ---\n"
        context_str += self._get_time_context()

        context_str += "\nPENDING TASKS (still processing):\n"
        for task in pending:
            context_str += f"- ID: {task.id} | Query: \"{task.query}\"\n"

        context_str += "\nCOMPLETED TASKS (ready to return):\n"
        for task in completed:
            result_preview = (task.result[:100] + "...") if task.result and len(task.result) > 100 else task.result
            error_info = f" | Error: {task.error}" if task.error else ""
            context_str += f"- ID: {task.id} | Query: \"{task.query}\" | Result: \"{result_preview}\"{error_info}\n"

        full_prompt = f"{system_prompt}\n{context_str}\n\nUSER STATUS QUERY: \"{query}\""
        result = self._call_ai(full_prompt)

        # Mark the matched task as consumed
        matched_task_id = result.get("matched_task_id")
        if matched_task_id:
            task_store.mark_consumed(matched_task_id)

        return result

    # Legacy method for backwards compatibility (not used anymore but kept for safety)
    def classify_intent(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy method - delegates to handle_tasks for backwards compatibility."""
        return self.handle_tasks(query, context)
