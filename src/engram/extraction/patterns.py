"""Regex patterns for memory extraction (ported from context_manager.py)."""

IMPORTANCE_PATTERNS: dict[str, list[str]] = {
    "preference": [
        r"(?:i |user )(?:prefer|like|want|always|never|hate)",
        r"(?:my |the )(?:style|preference|approach)",
        r"(?:don't|do not) (?:use|want|like)",
    ],
    "decision": [
        r"(?:decided|choosing|going with|picked|selected)",
        r"(?:the plan is|we will|let's go with)",
        r"(?:agreed|confirmed|approved)",
    ],
    "fact": [
        r"(?:the |this )(?:project|codebase|repo|app)",
        r"(?:uses|requires|depends on|built with)",
        r"(?:architecture|structure|pattern)",
    ],
    "error_fix": [
        r"(?:fixed|solved|resolved) (?:by|with|using)",
        r"(?:the (?:bug|error|issue) was)",
        r"(?:solution|workaround|fix):?",
    ],
    "pattern": [
        r"(?:always|never|must) (?:use|call|import)",
        r"(?:naming convention|code style)",
        r"(?:this function|this class|this module)",
    ],
}

TYPE_WEIGHTS: dict[str, int] = {
    "preference": 8,
    "decision": 7,
    "error_fix": 7,
    "fact": 6,
    "pattern": 6,
    "summary": 5,
}

HIGH_INDICATORS: list[str] = ["always", "never", "must", "critical", "important", "key"]
