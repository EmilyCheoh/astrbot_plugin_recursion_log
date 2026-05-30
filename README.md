# Recursion Log

Cross-window continuity through manually curated summaries — injected into the first message of every new conversation window.

## How It Works

1. During a conversation, save what matters with `rs add {text}`
2. When a new window opens, the plugin automatically injects the most recent entries into the first LLM request
3. No more cold starts

## Commands

| Command | Description |
|---|---|
| `rs add {text}` | Save a new entry (supports multi-line with `{}`) |
| `rs list` | Show the most recent entries (count set in config) |
| `rs list all` | Show all entries |
| `rs view <id>` | View a single entry's full content |
| `rs edit <id> {new text}` | Overwrite an entry's text |
| `rs delete <id>` | Delete an entry |

Entry IDs are stable — deleting an entry does not change other entries' IDs.

## Injection

On the first message of a new window (detected by context count), the plugin injects the most recent `display_count` entries wrapped in an XML tag:

```
<Recursion-Log>
The following are curated snapshots from previous conversation windows...

1. Entry text here
[05-30]

2. Another entry
[05-29]
</Recursion-Log>
```

Injection priority is `-498`, designed to appear below `FirstWindowInject` (`-499`) when both use `user_message_before`.

## Config

| Field | Type | Default | Description |
|---|---|---|---|
| `tag_name` | string | `Recursion-Log` | XML tag name wrapping the injected block |
| `header_text` | text | *(see config)* | Explanatory text before numbered entries |
| `display_count` | int | `5` | How many recent entries to inject |
| `inject_position` | string | `user_message_before` | Where to inject: `user_message_before`, `user_message_after`, or `system_prompt` |
| `date_format` | string | `MM-DD` | Timestamp display format |
| `initial_context_count` | int | `0` | Context count threshold for first-window detection |

## Data Storage

Entries are stored as JSON at `data/plugin_data/RecursionLog/entries.json`. Each entry:

```json
{
  "id": 1,
  "text": "Entry content here",
  "created_at": "2026-05-30T14:23:00+08:00"
}
```

The file can be edited directly for bulk operations or timestamp changes.
