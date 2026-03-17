# ulauncher-track

A [Ulauncher](https://ulauncher.io/) extension for tracking personal metrics — a lightweight quantified-self tool you can use without leaving your keyboard. Log runs, steps, pushups, meditation minutes, or any numeric measurement you care about. All data is stored locally in a SQLite database.

## Features

- **Instant logging** — open Ulauncher, type a metric name and value, press Enter
- **No setup** — new metric categories are created on the fly; nothing to configure
- **Rich summaries** — typing just a metric name shows all-time total, 7-day total, running average, last value, and time since last entry
- **History view** — inspect recent entries for any metric without leaving the launcher
- **Overview list** — see all your tracked metrics in one view
- **Purely local** — data never leaves your machine; stored in a plain SQLite file you own

## Requirements

- [Ulauncher](https://ulauncher.io/) 5.x with API v2 support
- Python 3.6+
- No third-party Python packages required (uses only the standard library)

## Installation

### 1. Clone or download

```bash
git clone https://github.com/dnewcome/ulauncher-track.git
```

Or download and extract the ZIP from the releases page.

### 2. Symlink into Ulauncher's extensions directory

```bash
ln -s /path/to/ulauncher-track \
      ~/.local/share/ulauncher/extensions/ulauncher-track
```

### 3. Enable the extension

1. Open Ulauncher preferences (`right-click tray icon → Preferences`)
2. Go to **Extensions**
3. The **Track Metrics** extension should appear — toggle it on
4. Optionally change the trigger keyword (default: `track`)

### 4. (Optional) Replace the icon

The bundled `images/icon.png` is a plain blue placeholder. Replace it with any 64×64 or 128×128 PNG you like and restart Ulauncher.

## Usage

Open Ulauncher (default: `Ctrl+Space`) and type `track` followed by a space.

### Log a value

```
track <metric> <value>
track <metric>: <value>
```

Both forms work — the colon is optional. The metric name is case-insensitive and normalized to lowercase. The value must be numeric (integer or decimal).

**Examples:**

```
track run 3.2
track pushups: 25
track steps 8400
track meditation: 20
track sleep 7.5
```

A result item appears showing what will be saved. Press **Enter** to confirm. If the metric name has never been used before, the item will say *"Create new metric…"* — there is nothing else to do; it is created automatically on first use.

### Check a metric's summary

Type just the metric name (no value) to see a stats summary:

```
track run
track pushups:
```

The result shows two lines of information:

```
run — total: 47.3 | last 7d: 12.1 (4 entries) | avg: 3.2
Last: 3.5  (2 days ago)  ·  15 entries all time  ·  type a value to log
```

- **total** — sum of all values ever logged for this metric
- **last 7d** — sum and entry count for the past 7 days
- **avg** — running average across all entries
- **Last** — the most recently logged value and how long ago it was recorded

### View recent history for a metric

```
track <metric>: list
track <metric> list
```

Shows the 8 most recent entries for that metric, each with its value and relative timestamp.

**Example:**

```
track run: list
```

```
run: 3.2     just now
run: 4.1     2 days ago
run: 3.0     5 days ago
run: 5.2     1 week ago
```

### List all metrics

```
track list
```

Shows every metric you have ever logged, sorted by most recently updated, with entry count and last value.

```
run          12 entries | Last: 3.2  (just now)
pushups      8 entries  | Last: 25   (3 days ago)
meditation   5 entries  | Last: 20   (1 week ago)
steps        3 entries  | Last: 8400 (2 weeks ago)
```

## Command reference

| Input | Action |
|---|---|
| `track` | Show usage hint |
| `track <metric>` | Show summary for that metric |
| `track <metric> <value>` | Prepare to log value → press Enter to save |
| `track <metric>: <value>` | Same as above (colon syntax) |
| `track list` | List all metrics |
| `track <metric>: list` | Show recent entries for metric |

## Data storage

All data is stored in a SQLite database at:

```
~/.local/share/ulauncher-track/metrics.db
```

The directory and database are created automatically on first use. The schema is simple and stable:

```sql
CREATE TABLE entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    metric     TEXT    NOT NULL,
    value      REAL    NOT NULL,
    note       TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Because it is plain SQLite, you can query, export, or back up your data with any standard tool:

```bash
# All runs, newest first
sqlite3 ~/.local/share/ulauncher-track/metrics.db \
  "SELECT created_at, value FROM entries WHERE metric='run' ORDER BY created_at DESC"

# Weekly pushup totals
sqlite3 ~/.local/share/ulauncher-track/metrics.db \
  "SELECT strftime('%Y-W%W', created_at) as week, SUM(value)
   FROM entries WHERE metric='pushups'
   GROUP BY week ORDER BY week"

# Export everything to CSV
sqlite3 -csv -header ~/.local/share/ulauncher-track/metrics.db \
  "SELECT * FROM entries ORDER BY created_at" > metrics.csv
```

## Debugging

Run Ulauncher in developer mode to see log output from the extension:

```bash
ulauncher --dev
```

Extension log lines are prefixed with the module name (`main`).

## License

MIT
