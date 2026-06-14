"""
RecursionLog - Cross-window continuity through structured state tracking.

Injects active entries from a structured JSON file into the first message
of every new conversation window. Entries are organized by sections
(e.g., states, deltas, unresolved threads) and managed via a Web UI.

No chat commands — all entry management is done through the Web UI.

Injection priority: -498 (runs after FirstWindowInject at -499,
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

TAG_NAME_PATTERN = re.compile(r"^[^<>\n\r]+$")

VALID_POSITIONS = ("user_message_before", "user_message_after")

DATE_FORMATS = {
    "MM-DD": "%m-%d",
    "YYYY-MM-DD": "%Y-%m-%d",
}

# Default data structure — array of sections
DEFAULT_DATA = [
    {
        "section_name": "states",
        "display_name": "Our States:",
        "enabled": "T",
        "entries": {},
    },
    {
        "section_name": "deltas",
        "display_name": "What Changed Recently:",
        "enabled": "T",
        "entries": {},
    },
    {
        "section_name": "unresolved",
        "display_name": "Unresolved Threads:",
        "enabled": "T",
        "entries": {},
    },
]


def _parse_position(value: str) -> str:
    pos = str(value).strip()
    return pos if pos in VALID_POSITIONS else "user_message_before"


@register(
    "RecursionLog",
    "FelisAbyssalis",
    "Cross-window continuity — structured state injection on first message",
    "2.0.0",
    "",
)
class RecursionLogPlugin(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

        # Config
        self._inject_entries = bool(config.get("inject_entries", True))
        self._initial_ctx_count = int(config.get("initial_context_count", 0))
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

        # Header & Footer
        raw_header = str(config.get("header_text", ""))
        self._header_text = raw_header.replace("\\n", "\n").strip()

        raw_inner_footer = str(config.get("inner_footer_text", ""))
        self._inner_footer_text = raw_inner_footer.replace("\\n", "\n").strip()

        raw_footer = str(config.get("footer_text", ""))
        self._footer_text = raw_footer.replace("\\n", "\n").strip()

        # Data file
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / "RecursionLog"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_file = data_dir / "entries.json"

        if not self._data_file.exists():
            self._data_file.write_text(
                json.dumps(DEFAULT_DATA, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        logger.info(
            f"[💜 RecursionLog] initialized "
            f"(position={self._inject_position}, "
            f"data={self._data_file})"
        )

    # -------------------------------------------------------------------
    # Data I/O
    # -------------------------------------------------------------------

    def _load_data(self) -> list[dict]:
        """Load the structured section data from JSON."""
        try:
            data = json.loads(self._data_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else DEFAULT_DATA
        except Exception as e:
            logger.error(f"[💜 RecursionLog] failed to load data: {e}")
            return DEFAULT_DATA

    # -------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------

    def _format_date(self, date_str: str) -> str:
        """Format a date string for display."""
        try:
            # Try parsing ISO format first
            dt = datetime.fromisoformat(date_str)
            return dt.strftime(self._date_format)
        except Exception:
            pass
        # Already in display format (e.g. "06-14"), return as-is
        return date_str

    def _build_section_block(self, section: dict) -> str | None:
        """Build injection text for a single section. Returns None if empty."""
        entries = section.get("entries", {})

        # Collect enabled entries
        active = []
        for _key, entry in entries.items():
            if entry.get("enabled", "T") == "T":
                active.append(entry)

        if not active:
            return None

        # Sort by date descending (most recent first)
        active.sort(key=lambda e: e.get("date", ""), reverse=True)

        # Display name (supports \n)
        display_name = section.get("display_name", section.get("section_name", ""))
        display_name = display_name.replace("\\n", "\n")

        lines = [display_name]
        for i, entry in enumerate(active, 1):
            content = entry.get("content", "")
            date = self._format_date(entry.get("date", ""))
            lines.append(f"{i}. {content} [Recorded on: {date}]")

        return "\n".join(lines)

    def _build_inject_block(self, data: list[dict]) -> str | None:
        """Build the full injection block from all sections."""
        section_blocks = []

        for section in data:
            if section.get("enabled", "T") != "T":
                continue
            block = self._build_section_block(section)
            if block is not None:
                section_blocks.append(block)

        if not section_blocks and not self._footer_text:
            return None

        parts = [f"<{self._tag_name}>"]

        if self._header_text:
            parts.append(self._header_text)
            parts.append("")

        if section_blocks:
            parts.append("\n\n".join(section_blocks))
            parts.append("")

        if self._inner_footer_text:
            parts.append(self._inner_footer_text)

        parts.append(f"</{self._tag_name}>")

        if self._footer_text:
            parts.append("")
            parts.append(self._footer_text)

        return "\n".join(parts)

    # -------------------------------------------------------------------
    # Injection
    # -------------------------------------------------------------------

    def _inject_text(self, req: ProviderRequest, text: str) -> None:
        if self._inject_position == "user_message_before":
            req.prompt = text + "\n\n" + (req.prompt or "")
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

            if not self._inject_entries:
                # Master switch off — only inject footer
                if self._footer_text:
                    self._inject_text(req, self._footer_text)
                return

            data = self._load_data()
            block = self._build_inject_block(data)

            if block is None:
                # Still inject footer if present
                if self._footer_text:
                    self._inject_text(req, self._footer_text)
                return

            self._inject_text(req, block)

            # Count active entries for logging
            active_count = 0
            for section in data:
                if section.get("enabled", "T") != "T":
                    continue
                for entry in section.get("entries", {}).values():
                    if entry.get("enabled", "T") == "T":
                        active_count += 1

            logger.info(
                f"[💜 RecursionLog] injected {active_count} active entries "
                f"@ {self._inject_position}"
            )
        except Exception as e:
            logger.error(f"[💜 RecursionLog] inject error: {e}", exc_info=True)

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    async def terminate(self):
        logger.info("[💜 RecursionLog] stopped")
