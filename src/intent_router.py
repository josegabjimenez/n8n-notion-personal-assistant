import os
import json
import subprocess
import shlex
from typing import Dict, Any

class IntentRouter:
    """Lightweight intent classifier that routes queries to specialized agents."""
    
    def __init__(self):
        self.cli_command = os.getenv("AI_CLI_COMMAND", "claude")
        self.router_prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            "prompts", 
            "ROUTER.md"
        )

    def _load_router_prompt(self) -> str:
        with open(self.router_prompt_path, "r") as f:
            return f.read()

    def classify(self, query: str) -> str:
        """
        Classify a query into a domain: 'tasks', 'contacts', or 'general'.
        Returns the domain string.
        """
        router_prompt = self._load_router_prompt()
        full_prompt = f"{router_prompt}\n\nUSER INPUT: \"{query}\"\n\nRespond with ONLY the domain name (tasks, contacts, or general):"
        
        cmd = shlex.split(self.cli_command)
        cmd.append(full_prompt)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout.strip().lower()
            
            # Clean up response - extract just the domain word
            for domain in ["tasks", "contacts", "general"]:
                if domain in output:
                    return domain
            
            # Default to general if unclear
            return "general"
            
        except subprocess.CalledProcessError:
            # On error, default to general
            return "general"
