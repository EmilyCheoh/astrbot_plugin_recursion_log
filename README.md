# Recursion Log

Cross-window continuity through structured state tracking — injected into the first message of every new conversation window.

The log is not a journal. It is a diff: what is happening, what changed, and what remains unresolved.

## How It Works

1. Entries are organized into sections (e.g., States, Deltas, Unresolved Threads) in a JSON file
2. Each section and entry can be individually enabled/disabled
3. When a new window opens, the plugin injects all active entries into the first LLM request
4. Entry management is done through the Web UI — no chat commands

## Data Structure

Entries are stored at `data/plugin_data/RecursionLog/entries.json`:

```json
[
  {
    "section_name": "states",
    "display_name": "Our States:",
    "enabled": "T",
    "entries": {
      "entry_1": {
        "content": "Entry text here",
        "date": "06-14",
        "enabled": "T"
      }
    }
  }
]
```

### Section Fields

| Field | Description |
|---|---|
| `section_name` | Internal identifier (used by code, not displayed) |
| `display_name` | Displayed as section header in the injected block (supports `\n`) |
| `enabled` | `T` or `F` — disabled sections are skipped entirely |
| `entries` | Object of entries keyed by `entry_1`, `entry_2`, etc. |

### Entry Fields

| Field | Description |
|---|---|
| `content` | The entry text |
| `date` | Date string (displayed as-is or formatted per config) |
| `enabled` | `T` or `F` — disabled entries are skipped |

## Injection

On the first message of a new window (detected by context count), the plugin injects active entries wrapped in an XML tag:

```
<Recursion-Log>
Header text...

Our States:
1. Entry one [06-14]
2. Entry two [06-12]

What Changed Recently:
1. Entry three [06-13]

Inner footer text...
</Recursion-Log>

Outer footer text...
```

- Sections with no active entries are skipped entirely
- Disabled sections (`enabled: "F"`) are skipped entirely
- Injection priority is `-498`, designed to appear below `FirstWindowInject` (`-499`)

## Config

| Field | Type | Default | Description |
|---|---|---|---|
| `tag_name` | string | `Recursion-Log` | XML tag name wrapping the injected block |
| `header_text` | text | *(empty)* | Text before the first section (supports `\n`) |
| `inject_position` | string | `user_message_before` | Where to inject: `user_message_before` or `user_message_after` |
| `date_format` | string | `MM-DD` | Timestamp display format |
| `inner_footer_text` | text | *(empty)* | Text after the last section, inside the tag |
| `footer_text` | text | *(see config)* | Text after the closing tag |
| `initial_context_count` | int | `2` | Context count threshold for first-window detection |
