"""
RecursionLog - Cross-window continuity through manually curated summaries.

Provides `rs` commands to manage entries (add, list, view, edit, delete)
and injects the most recent k entries into the first message of every
new conversation window.

Injection priority: -498 (runs before FirstWindowInject at -499,
so that FirstWindowInject's content appears above the recursion log
in the final prompt when both use user_message_before).

F(A) = A(F)
"""

import json
import re
from datetime import datetime
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

TAG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
BRACE_PATTERN = re.compile(r"\{(.*)\}", flags=re.DOTALL)

VALID_POSITIONS = ("user_message_before", "user_message_after", "system_prompt")

DATE_FORMATS = {
    "MM-DD": "%m-%d",
    "YYYY-MM-DD": "%Y-%m-%d",
}


def _parse_position(value: str) -> str:
    pos = str(value).strip()
    return pos if pos in VALID_POSITIONS else "user_message_before"


@register(
    "RecursionLog",
    "FelisAbyssalis",
    "Cross-window continuity — manual summaries injected on first message",
    "1.0.0",
    "",
)
class RecursionLogPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # Config
        self._initial_ctx_count = int(config.get("initial_context_count", 0))
        self._display_count = int(config.get("display_count", 5))
        self._inject_position = _parse_position(
            config.get("inject_position", "user_message_before")
        )
        self._date_format = DATE_FORMATS.get(
            config.get("date_format", "MM-DD"), "%m-%d"
        )

        # Tag
        tag_name = str(config.get("tag_name", "Recursion-Log")).strip()
        if not tag_name or not TAG_NAME_PATTERN.match(tag_name):
            tag_name = "Recursion-Log"
        self._tag_name = tag_name

        # Header
        raw_header = str(config.get("header_text", ""))
        self._header_text = raw_header.replace("\\n", "\n").strip()

        # Data file
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / "RecursionLog"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_file = data_dir / "entries.json"

        if not self._data_file.exists():
            self._data_file.write_text("[]", encoding="utf-8")

        logger.info(
            f"[RecursionLog] initialized "
            f"(display={self._display_count}, "
            f"position={self._inject_position}, "
            f"data={self._data_file})"
        )

    # -------------------------------------------------------------------
    # Data I/O
    # -------------------------------------------------------------------

    def _load_entries(self) -> list[dict]:
        try:
            data = json.loads(self._data_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"[RecursionLog] failed to load entries: {e}")
            return []

    def _save_entries(self, entries: list[dict]) -> None:
        try:
            self._data_file.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[RecursionLog] failed to save entries: {e}")

    def _next_id(self, entries: list[dict]) -> int:
        if not entries:
            return 1
        return max(e.get("id", 0) for e in entries) + 1

    # -------------------------------------------------------------------
    # Text extraction helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_braced(text: str) -> str | None:
        """Extract content from {braces}. Returns None if no braces found."""
        m = BRACE_PATTERN.search(text)
        return m.group(1).strip() if m else None

    # -------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------

    def _format_date(self, iso_str: str) -> str:
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime(self._date_format)
        except Exception:
            return iso_str

    def _format_entry_display(self, entry: dict, index: int) -> str:
        """Format a single entry for display in QQ messages."""
        text = entry.get("text", "")
        date = self._format_date(entry.get("created_at", ""))
        return f"{index}. (id={entry.get('id', '?')}) {text}\n[{date}]"

    def _format_entry_inject(self, entry: dict, index: int) -> str:
        """Format a single entry for injection into LLM context."""
        text = entry.get("text", "")
        date = self._format_date(entry.get("created_at", ""))
        return f"{index}. {text}\n[{date}]"

    def _build_inject_block(self, entries: list[dict]) -> str:
        """Build the full injection block with tag, header, and entries."""
        recent = sorted(
            entries, key=lambda e: e.get("created_at", ""), reverse=True
        )[: self._display_count]

        parts = [f"<{self._tag_name}>"]
        if self._header_text:
            parts.append(self._header_text)
            parts.append("")

        for i, entry in enumerate(recent, 1):
            parts.append(self._format_entry_inject(entry, i))
            parts.append("")

        parts.append(f"</{self._tag_name}>")
        return "\n".join(parts)

    # -------------------------------------------------------------------
    # Injection
    # -------------------------------------------------------------------

    def _inject_text(self, req: ProviderRequest, text: str) -> None:
        if self._inject_position == "user_message_before":
            req.prompt = text + "\n\n" + (req.prompt or "")
        elif self._inject_position == "system_prompt":
            req.system_prompt = (req.system_prompt or "") + "\n\n" + text
        else:  # user_message_after
            req.prompt = (req.prompt or "") + "\n\n" + text

    @filter.on_llm_request(priority=-498)
    async def handle_inject(
        self, event: AstrMessageEvent, req: ProviderRequest
    ):
        try:
            ctx_count = len(req.contexts) if req.contexts else 0
            if ctx_count > self._initial_ctx_count:
                return

            entries = self._load_entries()
            if not entries:
                return

            block = self._build_inject_block(entries)
            self._inject_text(req, block)

            logger.info(
                f"[RecursionLog] injected {min(len(entries), self._display_count)} "
                f"entries @ {self._inject_position} "
                f"(contexts: {ctx_count})"
            )
        except Exception as e:
            logger.error(f"[RecursionLog] inject error: {e}", exc_info=True)

    # -------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------

    @filter.command_group("rs")
    def rs(self):
        pass

    @rs.command("add")
    async def rs_add(self, event: AstrMessageEvent):
        """Add a new entry. Usage: rs add {your text here}"""
        raw = event.message_str
        # Strip the "rs add" prefix
        prefix_match = re.match(r"rs\s+add\s*", raw, re.IGNORECASE)
        if not prefix_match:
            yield event.plain_result("Usage: rs add {text}")
            return

        remainder = raw[prefix_match.end():]
        text = self._extract_braced(remainder)
        if text is None:
            text = remainder.strip()

        if not text:
            yield event.plain_result("Usage: rs add {text}")
            return

        entries = self._load_entries()
        new_entry = {
            "id": self._next_id(entries),
            "text": text,
            "created_at": datetime.now().astimezone().isoformat(),
        }
        entries.append(new_entry)
        self._save_entries(entries)

        date = self._format_date(new_entry["created_at"])
        yield event.plain_result(
            f"Saved (id={new_entry['id']}, {date}):\n{text}"
        )

    @rs.command("list")
    async def rs_list(self, event: AstrMessageEvent):
        """List recent entries. Usage: rs list [all]"""
        raw = event.message_str
        show_all = "all" in raw.lower().split()

        entries = self._load_entries()
        if not entries:
            yield event.plain_result("No entries.")
            return

        sorted_entries = sorted(
            entries, key=lambda e: e.get("created_at", ""), reverse=True
        )

        if not show_all:
            sorted_entries = sorted_entries[: self._display_count]

        lines = []
        for i, entry in enumerate(sorted_entries, 1):
            lines.append(self._format_entry_display(entry, i))

        total = len(entries)
        header = f"All {total} entries:" if show_all else f"Recent {len(sorted_entries)}/{total}:"
        yield event.plain_result(header + "\n\n" + "\n\n".join(lines))

    @rs.command("view")
    async def rs_view(self, event: AstrMessageEvent):
        """View a single entry by id. Usage: rs view <id>"""
        raw = event.message_str
        parts = raw.split()

        entry_id = None
        for p in parts:
            try:
                entry_id = int(p)
                break
            except ValueError:
                continue

        if entry_id is None:
            yield event.plain_result("Usage: rs view <id>")
            return

        entries = self._load_entries()
        target = next((e for e in entries if e.get("id") == entry_id), None)

        if target is None:
            yield event.plain_result(f"Entry id={entry_id} not found.")
            return

        date = self._format_date(target.get("created_at", ""))
        yield event.plain_result(
            f"Entry id={entry_id} [{date}]:\n\n{target.get('text', '')}"
        )

    @rs.command("edit")
    async def rs_edit(self, event: AstrMessageEvent):
        """Edit an entry's text. Usage: rs edit <id> {new text}"""
        raw = event.message_str
        prefix_match = re.match(r"rs\s+edit\s+(\d+)\s*", raw, re.IGNORECASE)
        if not prefix_match:
            yield event.plain_result("Usage: rs edit <id> {new text}")
            return

        entry_id = int(prefix_match.group(1))
        remainder = raw[prefix_match.end():]
        text = self._extract_braced(remainder)
        if text is None:
            text = remainder.strip()

        if not text:
            yield event.plain_result("Usage: rs edit <id> {new text}")
            return

        entries = self._load_entries()
        target = next((e for e in entries if e.get("id") == entry_id), None)

        if target is None:
            yield event.plain_result(f"Entry id={entry_id} not found.")
            return

        target["text"] = text
        self._save_entries(entries)

        yield event.plain_result(f"Updated id={entry_id}:\n{text}")

    @rs.command("delete")
    async def rs_delete(self, event: AstrMessageEvent):
        """Delete an entry by id. Usage: rs delete <id>"""
        raw = event.message_str
        parts = raw.split()

        entry_id = None
        for p in parts:
            try:
                entry_id = int(p)
                break
            except ValueError:
                continue

        if entry_id is None:
            yield event.plain_result("Usage: rs delete <id>")
            return

        entries = self._load_entries()
        original_len = len(entries)
        entries = [e for e in entries if e.get("id") != entry_id]

        if len(entries) == original_len:
            yield event.plain_result(f"Entry id={entry_id} not found.")
            return

        self._save_entries(entries)
        yield event.plain_result(f"Deleted id={entry_id}.")

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    async def terminate(self):
        logger.info("[RecursionLog] stopped")
