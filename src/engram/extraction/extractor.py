"""Context extraction — pulls memories from free-form text."""

from __future__ import annotations

import re
from typing import Any

from engram.extraction.patterns import HIGH_INDICATORS, IMPORTANCE_PATTERNS, TYPE_WEIGHTS


class ContextExtractor:
    """Scan text for memory-worthy sentences."""

    def extract(self, text: str, project: str | None = None) -> list[dict[str, Any]]:
        """Return a list of candidate memory dicts extracted from *text*."""
        extracted: list[dict[str, Any]] = []
        sentences = re.split(r"[.!?\n]", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue

            for mem_type, patterns in IMPORTANCE_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, sentence, re.IGNORECASE):
                        importance = self._calculate_importance(sentence, mem_type)
                        extracted.append(
                            {
                                "type": mem_type,
                                "content": sentence,
                                "importance": importance,
                                "project": project,
                            }
                        )
                        break  # one match per sentence
                else:
                    continue
                break

        return extracted

    @staticmethod
    def _calculate_importance(text: str, mem_type: str) -> int:
        importance = 5
        lower = text.lower()
        for indicator in HIGH_INDICATORS:
            if indicator in lower:
                importance += 2
                break
        importance = max(importance, TYPE_WEIGHTS.get(mem_type, 5))
        return min(10, importance)
