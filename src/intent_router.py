import os
import re
import logging
from typing import Optional

from ai_client import AIClient

logger = logging.getLogger("IntentRouter")


class IntentRouter:
    """Lightweight intent classifier that routes queries to specialized agents."""

    # Keywords that STRONGLY indicate a domain (unambiguous)
    STRONG_TASK_KEYWORDS = {
        "tarea", "tareas", "pendiente", "pendientes", "to-do", "todo",
        "deadline", "vencimiento", "completada", "completado"
    }

    STRONG_CONTACT_KEYWORDS = {
        "contacto", "contactos", "cumpleaños", "cumple", "email", "correo",
        "teléfono", "telefono", "celular", "hermano", "hermana", "mamá", "mama",
        "papá", "papa", "familia", "amigo", "amiga", "amigos", "amigas"
    }

    STRONG_GENERAL_KEYWORDS = {
        "hola", "gracias", "ayuda", "puedes", "hacer"
    }

    # Keywords that are AMBIGUOUS alone but clarified by context
    # Format: (ambiguous_word, context_word) -> domain
    CONTEXTUAL_PATTERNS = {
        # "crear/añadir + tarea" -> tasks
        ("crear", "tarea"): "tasks",
        ("añadir", "tarea"): "tasks",
        ("agregar", "tarea"): "tasks",
        ("nueva", "tarea"): "tasks",
        ("nuevo", "pendiente"): "tasks",
        # "crear/añadir + contacto" -> contacts
        ("crear", "contacto"): "contacts",
        ("añadir", "contacto"): "contacts",
        ("agregar", "contacto"): "contacts",
        ("nuevo", "contacto"): "contacts",
        ("nueva", "persona"): "contacts",
        # "recordar/recuerda + me" -> tasks (reminder = task)
        ("recuérdame", None): "tasks",
        ("recuerdame", None): "tasks",
        ("recordarme", None): "tasks",
        ("recordatorio", None): "tasks",
        # "quién es" -> contacts
        ("quién", "es"): "contacts",
        ("quien", "es"): "contacts",
        # "qué tareas" -> tasks
        ("qué", "tareas"): "tasks",
        ("que", "tareas"): "tasks",
        ("cuántas", "tareas"): "tasks",
        ("cuantas", "tareas"): "tasks",
        # "qué/cuántos contactos" -> contacts
        ("qué", "contactos"): "contacts",
        ("que", "contactos"): "contacts",
        ("cuántos", "contactos"): "contacts",
        ("cuantos", "contactos"): "contacts",
    }

    # Phrases that strongly indicate tasks (action-oriented)
    TASK_PHRASES = [
        r"marca(?:r)?\s+como\s+(?:completad[ao]|hech[ao]|termin)",
        r"borra(?:r)?\s+(?:la\s+)?tarea",
        r"elimina(?:r)?\s+(?:la\s+)?tarea",
        r"edita(?:r)?\s+(?:la\s+)?tarea",
        r"(?:tengo|hay)\s+(?:para|pendiente)",
        r"para\s+(?:hoy|mañana|manana|esta\s+semana)",
    ]

    # Phrases that strongly indicate contacts
    CONTACT_PHRASES = [
        r"cuál\s+es\s+(?:el\s+)?(?:email|correo|teléfono|telefono|celular)",
        r"cual\s+es\s+(?:el\s+)?(?:email|correo|teléfono|telefono|celular)",
        r"cuándo\s+(?:cumple|nació)",
        r"cuando\s+(?:cumple|nació|nacio)",
        r"dime\s+(?:sobre|de)\s+(?:mi[s]?\s+)?(?:amigo|familia|contacto)",
    ]

    def __init__(self, ai_client: Optional[AIClient] = None):
        self.ai_client = ai_client or AIClient()
        self.router_prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "ROUTER.md"
        )
        # Compile regex patterns for efficiency
        self._task_patterns = [re.compile(p, re.IGNORECASE) for p in self.TASK_PHRASES]
        self._contact_patterns = [re.compile(p, re.IGNORECASE) for p in self.CONTACT_PHRASES]

    def _load_router_prompt(self) -> str:
        with open(self.router_prompt_path, "r") as f:
            return f.read()

    def _classify_fast(self, query: str) -> Optional[str]:
        """
        Fast keyword-based classification. Returns None if uncertain.
        Saves 2-3 seconds by avoiding AI call for clear-cut cases.
        """
        query_lower = query.lower()
        words = set(re.findall(r'\w+', query_lower))

        # Check phrase patterns first (most specific)
        for pattern in self._task_patterns:
            if pattern.search(query_lower):
                logger.info(f"Fast classification: tasks (phrase match)")
                return "tasks"

        for pattern in self._contact_patterns:
            if pattern.search(query_lower):
                logger.info(f"Fast classification: contacts (phrase match)")
                return "contacts"

        # Check contextual patterns (word pairs)
        for (word1, word2), domain in self.CONTEXTUAL_PATTERNS.items():
            if word1 in words:
                if word2 is None or word2 in words:
                    logger.info(f"Fast classification: {domain} (contextual: {word1}+{word2})")
                    return domain

        # Check strong keywords
        task_matches = words & self.STRONG_TASK_KEYWORDS
        contact_matches = words & self.STRONG_CONTACT_KEYWORDS
        general_matches = words & self.STRONG_GENERAL_KEYWORDS

        # Only classify if there's a clear winner
        if task_matches and not contact_matches:
            logger.info(f"Fast classification: tasks (keywords: {task_matches})")
            return "tasks"

        if contact_matches and not task_matches:
            logger.info(f"Fast classification: contacts (keywords: {contact_matches})")
            return "contacts"

        # Check for greetings (short queries with general keywords)
        if general_matches and len(words) <= 4 and not task_matches and not contact_matches:
            logger.info(f"Fast classification: general (keywords: {general_matches})")
            return "general"

        # Ambiguous - need AI classification
        logger.info(f"Fast classification: uncertain, falling back to AI")
        return None

    def classify(self, query: str) -> str:
        """
        Classify a query into a domain: 'tasks', 'contacts', 'status', or 'general'.
        Uses fast keyword matching first, falls back to AI for ambiguous cases.
        Returns the domain string.
        """
        # Try fast classification first (saves 2-3 seconds)
        fast_result = self._classify_fast(query)
        if fast_result:
            return fast_result

        # Fall back to AI classification for ambiguous queries
        router_prompt = self._load_router_prompt()
        full_prompt = f"{router_prompt}\n\nUSER INPUT: \"{query}\"\n\nRespond with ONLY the domain name (tasks, contacts, status, or general):"

        domain = self.ai_client.call_for_classification(full_prompt)
        logger.info(f"AI classification: {domain}")
        return domain
