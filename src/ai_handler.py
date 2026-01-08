import os
import json
import subprocess
import shlex
import datetime
from typing import List, Dict, Any

class AIHandler:
    def __init__(self):
        self.cli_command = os.getenv("AI_CLI_COMMAND", "claude")
        self.claude_md_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "CLAUDE.md")

    def _load_system_prompt(self) -> str:
        with open(self.claude_md_path, "r") as f:
            return f.read()

    def classify_intent(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = self._load_system_prompt()
        
        # Build Context String
        # Get current time in Colombia (UTC-5)
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/Bogota")
        except ImportError:
            # Fallback for systems without zoneinfo/tzdata (UTC-5)
            tz = datetime.timezone(datetime.timedelta(hours=-5))

        now = datetime.datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d %A")
        time_str = now.strftime("%H:%M:%S")

        context_str = f"\n\n--- DYNAMIC CONTEXT ---\n"
        context_str += f"CURRENT DATE: {today_str}\n"
        context_str += f"CURRENT TIME: {time_str} (Timezone: America/Bogota)\n"
        
        context_str += "\nAVAILABLE AREAS:\n"
        for area in context.get("areas", []):
            context_str += f"- {area['name']} (ID: {area['id']})\n"
            
        context_str += "\nAVAILABLE PROJECTS:\n"
        for proj in context.get("projects", []):
            context_str += f"- {proj['name']} (ID: {proj['id']})\n"
            
        context_str += "\nEXISTING TASKS (Recent/Active):\n"
        for task in context.get("tasks", []):
            context_str += f"- {task['name']} (ID: {task['id']})\n"

        full_prompt = f"{system_prompt}\n{context_str}\n\nUSER INPUT: \"{query}\""

        # Execute External CLI
        # We assume the CLI accepts the prompt as the last argument or via some flag.
        # User specified "AI_CLI_COMMAND".
        # If using `claude` CLI, usually it's `claude "prompt"`.
        # If using `gh model`, it might be `gh model prompt "prompt"`.
        # We'll try to append the prompt as an argument.
        
        cmd = shlex.split(self.cli_command)
        cmd.append(full_prompt)
        
        try:
            # Capture stdout
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            
            # Simple attempt to find JSON if wrapped in markdown code blocks
            if "```json" in output:
                output = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                output = output.split("```")[1].strip()
                
            return json.loads(output)
            
        except subprocess.CalledProcessError as e:
            return {
                "intent": "query",
                "response": f"Lo siento, hubo un error al procesar tu solicitud con la IA. Error: {e.stderr}",
                "task": None
            }
        except json.JSONDecodeError:
            # Fallback if AI didn't return valid JSON
            # We might want to just return the raw text as a query response if it looks like English/Spanish
            # But strictly following the schema is better.
            return {
                "intent": "query",
                "response": "Lo siento, la respuesta de la IA no fue un formato válido. " + output[:100],
                "task": None
            }
