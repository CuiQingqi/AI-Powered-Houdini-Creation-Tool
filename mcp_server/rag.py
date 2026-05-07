"""
RAG (Retrieval-Augmented Generation) for Obsidian vault.

- Indexes .md files from the Obsidian vault
- Searches by keyword / semantic similarity
- Saves completed workflows as structured notes
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ObsidianRAG:
    """Simple file-based RAG over an Obsidian vault."""

    def __init__(self, vault_path: str = ""):
        self.vault_path = Path(vault_path) if vault_path else None
        self._index: List[dict] = []
        self._index_time: float = 0
        self._index_ttl: float = 300  # Reindex every 5 min

    @property
    def available(self) -> bool:
        return self.vault_path is not None and self.vault_path.exists()

    def _ensure_index(self):
        """(Re)build the file index if needed."""
        if not self.available:
            return
        if time.time() - self._index_time < self._index_ttl and self._index:
            return

        self._index = []
        for md_file in self.vault_path.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                # Skip very large files
                if len(content) > 100_000:
                    continue
                self._index.append({
                    "path": str(md_file.relative_to(self.vault_path)),
                    "name": md_file.stem,
                    "content": content,
                    "size": len(content),
                    "mtime": md_file.stat().st_mtime,
                })
            except Exception:
                pass
        self._index_time = time.time()

    def search(self, query: str, limit: int = 10) -> List[dict]:
        """Search the vault for relevant notes.

        Simple keyword-based search with TF-like scoring.
        """
        if not self.available:
            return []

        self._ensure_index()
        query_lower = query.lower()
        keywords = [k.strip() for k in query_lower.split() if len(k.strip()) > 1]

        scored = []
        for doc in self._index:
            content_lower = doc["content"].lower()
            name_lower = doc["name"].lower()

            # Score: title matches + content keyword frequency
            score = 0
            if query_lower in name_lower:
                score += 20
            if query_lower in content_lower:
                score += 10

            for kw in keywords:
                score += content_lower.count(kw)

            if score > 0:
                scored.append({
                    "name": doc["name"],
                    "path": doc["path"],
                    "score": score,
                    "snippet": self._get_snippet(doc["content"], query_lower, keywords),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def _get_snippet(self, content: str, query: str, keywords: List[str]) -> str:
        """Extract a relevant snippet around the first keyword match."""
        content_lower = content.lower()
        best_pos = -1

        # Find first keyword match
        for kw in keywords:
            pos = content_lower.find(kw)
            if pos >= 0 and (best_pos < 0 or pos < best_pos):
                best_pos = pos

        if best_pos < 0:
            return content[:200]

        start = max(0, best_pos - 80)
        end = min(len(content), best_pos + 120)
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet.strip()

    def save_workflow_note(self, name: str, content: str, folder: str = "Houdini_AI") -> str:
        """Save a workflow as a markdown note in the Obsidian vault.

        Args:
            name: Note name (becomes the .md filename).
            content: Markdown content.
            folder: Subfolder within the vault.

        Returns:
            Path to the saved note, or empty string on failure.
        """
        if not self.available:
            return ""

        dest_dir = self.vault_path / folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize filename
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)[:100]
        note_path = dest_dir / f"{safe_name}.md"

        note_path.write_text(content, encoding="utf-8")
        return str(note_path.relative_to(self.vault_path))

    def workflow_to_markdown(self, state_dict: dict) -> str:
        """Convert a workflow state dict to well-formatted markdown."""
        md = f"""---
tags: [houdini, procedural, workflow]
created: {time.strftime('%Y-%m-%d %H:%M')}
status: {state_dict.get('phase', 'unknown')}
tasks_total: {state_dict.get('total_tasks', 0)}
tasks_completed: {state_dict.get('completed_tasks', 0)}
---

# {state_dict.get('name', 'Untitled Workflow')}

## Prompt
{state_dict.get('user_prompt', '')}

## Requirement
{state_dict.get('detailed_requirement', '')}

## Modules
"""
        for m in state_dict.get("modules", []):
            md += f"\n### {m.get('module_id', '')}: {m.get('module_name', '')}\n"
            md += f"{m.get('description', '')}\n"

            for op in m.get("operations", []):
                op_name = op.get("operation_name", "") if isinstance(op, dict) else str(op)
                md += f"\n#### {op_name}\n"

                for t in op.get("tasks", []) if isinstance(op, dict) else []:
                    status_icon = "✅" if t.get("status") == "done" else ("🔄" if t.get("status") == "running" else "⬜")
                    md += f"- {status_icon} **{t.get('task_id', '?')}**: {t.get('action_type', '')} — {t.get('comment', t.get('operation_name', ''))}\n"

        md += f"\n## Progress\n"
        md += f"- Completed: {state_dict.get('completed_tasks', 0)}/{state_dict.get('total_tasks', 0)}\n"
        md += f"- Failed: {state_dict.get('failed_tasks', 0)}\n"
        md += f"- Phase: {state_dict.get('phase', 'unknown')}\n"

        return md


# ── Singleton ───────────────────────────────────────────────────────

_rag_instance: Optional[ObsidianRAG] = None


def get_rag(vault_path: str = "") -> ObsidianRAG:
    global _rag_instance
    if vault_path:
        _rag_instance = ObsidianRAG(vault_path)
    if _rag_instance is None:
        _rag_instance = ObsidianRAG("")
    return _rag_instance
