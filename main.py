import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction

logger = logging.getLogger(__name__)

DB_DIR = os.path.expanduser('~/.local/share/ulauncher-track')
DB_PATH = os.path.join(DB_DIR, 'metrics.db')


def get_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric TEXT NOT NULL,
            value REAL NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_metric ON entries(metric)')
    conn.commit()
    return conn


def time_ago(dt_str):
    """Convert an ISO timestamp string to a human-friendly relative string."""
    try:
        dt = datetime.fromisoformat(dt_str)
        # SQLite stores as local time (no tz info); treat as local
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return 'just now'
        if seconds < 3600:
            m = seconds // 60
            return f'{m} minute{"s" if m != 1 else ""} ago'
        if seconds < 86400:
            h = seconds // 3600
            return f'{h} hour{"s" if h != 1 else ""} ago'
        d = seconds // 86400
        return f'{d} day{"s" if d != 1 else ""} ago'
    except Exception:
        return dt_str


def fmt(v):
    """Format a float cleanly — drop decimal if whole number."""
    return str(int(v)) if v == int(v) else f'{v:g}'


def metric_summary(conn, metric):
    """Return a dict of stats for the metric, or None if no entries."""
    row = conn.execute(
        'SELECT COUNT(*), SUM(value), AVG(value), value, created_at '
        'FROM entries WHERE metric = ? ORDER BY created_at DESC LIMIT 1',
        (metric,)
    ).fetchone()
    if not row or row[0] == 0:
        return None
    count, total, avg, last_val, last_ts = row

    week_row = conn.execute(
        "SELECT SUM(value), COUNT(*) FROM entries "
        "WHERE metric = ? AND created_at >= datetime('now', '-7 days')",
        (metric,)
    ).fetchone()
    week_total, week_count = week_row if week_row else (0, 0)

    return {
        'count': count,
        'total': total,
        'avg': avg,
        'last_val': last_val,
        'last_ago': time_ago(last_ts),
        'week_total': week_total or 0,
        'week_count': week_count or 0,
    }


def recent_entries(conn, metric, limit=5):
    """Return list of (value, created_at) for the most recent entries."""
    return conn.execute(
        'SELECT value, created_at FROM entries WHERE metric = ? ORDER BY created_at DESC LIMIT ?',
        (metric, limit)
    ).fetchall()


def all_metrics(conn):
    """Return list of (metric, count, last_value, last_ts) sorted by last entry."""
    return conn.execute('''
        SELECT metric, COUNT(*) as cnt, value, created_at
        FROM entries
        GROUP BY metric
        ORDER BY created_at DESC
    ''').fetchall()


def parse_query(query):
    """
    Parse the user query into (metric, value_or_command).

    Accepts:
      <metric>              → (metric, None)
      <metric>:             → (metric, None)
      <metric>: <val>       → (metric, val_str)
      <metric> <val>        → (metric, val_str)
      <metric>: list        → (metric, 'list')
      list                  → ('list', None)
    """
    if not query:
        return None, None

    query = query.strip()

    # Special top-level command
    if query.lower() == 'list':
        return 'list', None

    # Split on optional colon then whitespace, or plain whitespace
    # Pattern: <word>[:][ <rest>]
    m = re.match(r'^(\S+?)(?::)?\s+(.+)$', query)
    if m:
        metric = m.group(1).lower().rstrip(':')
        rest = m.group(2).strip()
        return metric, rest

    # Just a metric name (possibly with trailing colon)
    metric = query.lower().rstrip(':')
    return metric, None


def format_value(val_str):
    """Try to parse val_str as a number. Return (float, display_str) or (None, None)."""
    try:
        f = float(val_str)
        display = str(int(f)) if f == int(f) else str(f)
        return f, display
    except (ValueError, TypeError):
        return None, None


class TrackExtension(Extension):

    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())


class KeywordQueryEventListener(EventListener):

    def on_event(self, event, extension):
        query = event.get_argument() or ''
        metric, rest = parse_query(query)

        try:
            conn = get_db()
        except Exception as e:
            logger.error('DB error: %s', e)
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Database error',
                    description=str(e),
                    on_enter=DoNothingAction()
                )
            ])

        # Empty query — show usage hint
        if not metric:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Track a metric',
                    description='Type: track <metric> <value>  |  track list',
                    on_enter=DoNothingAction()
                )
            ])

        # `track list` — show all metrics
        if metric == 'list':
            rows = all_metrics(conn)
            conn.close()
            if not rows:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='No metrics tracked yet',
                        description='Type: track <metric> <value> to get started',
                        on_enter=DoNothingAction()
                    )
                ])
            items = []
            for row_metric, cnt, last_val, last_ts in rows:
                val_str = str(int(last_val)) if last_val == int(last_val) else str(last_val)
                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=f'{row_metric}',
                    description=f'{cnt} entries | Last: {val_str}  ({time_ago(last_ts)})',
                    on_enter=DoNothingAction()
                ))
            return RenderResultListAction(items)

        # `track <metric>: list` — show recent entries for metric
        if rest and rest.lower() == 'list':
            rows = recent_entries(conn, metric, limit=8)
            conn.close()
            if not rows:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name=f'No entries for "{metric}"',
                        description='Nothing logged yet',
                        on_enter=DoNothingAction()
                    )
                ])
            items = []
            for val, ts in rows:
                val_str = str(int(val)) if val == int(val) else str(val)
                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=f'{metric}: {val_str}',
                    description=time_ago(ts),
                    on_enter=DoNothingAction()
                ))
            return RenderResultListAction(items)

        # `track <metric>` — show summary, no value yet
        if rest is None:
            summary = metric_summary(conn, metric)
            conn.close()
            if summary:
                s = summary
                name_line = (
                    f'{metric}  \u2014  '
                    f'total: {fmt(s["total"])}  |  '
                    f'last 7d: {fmt(s["week_total"])} ({s["week_count"]} entries)  |  '
                    f'avg: {fmt(s["avg"])}'
                )
                desc_line = (
                    f'Last: {fmt(s["last_val"])}  ({s["last_ago"]})  \u00b7  '
                    f'{s["count"]} entries all time  \u00b7  '
                    f'type a value to log'
                )
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name=name_line,
                        description=desc_line,
                        on_enter=DoNothingAction()
                    )
                ])
            else:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name=f'New metric: "{metric}"',
                        description='No entries yet — type a value to start tracking',
                        on_enter=DoNothingAction()
                    )
                ])

        # `track <metric> <value>` — ready to log
        num_val, display = format_value(rest)
        conn.close()

        if num_val is None:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name=f'Invalid value: "{rest}"',
                    description='Value must be a number (e.g. 3.2, 42)',
                    on_enter=DoNothingAction()
                )
            ])

        # Check if metric is new (for label purposes) — reopen briefly
        conn2 = get_db()
        summary = metric_summary(conn2, metric)
        conn2.close()

        if summary:
            label = f'Log {display} → {metric}  ({summary["count"]} entries so far)'
        else:
            label = f'Create new metric "{metric}" and log {display}'

        return RenderResultListAction([
            ExtensionResultItem(
                icon='images/icon.png',
                name=label,
                description='Press Enter to save',
                on_enter=ExtensionCustomAction(
                    {'action': 'log', 'metric': metric, 'value': num_val},
                    keep_app_open=False
                )
            )
        ])


class ItemEnterEventListener(EventListener):

    def on_event(self, event, extension):
        data = event.get_data()
        if not data or data.get('action') != 'log':
            return HideWindowAction()

        metric = data['metric']
        value = data['value']

        try:
            conn = get_db()
            conn.execute(
                'INSERT INTO entries (metric, value) VALUES (?, ?)',
                (metric, value)
            )
            conn.commit()
            conn.close()
            logger.info('Logged %s = %s', metric, value)
        except Exception as e:
            logger.error('Failed to log entry: %s', e)

        return HideWindowAction()


if __name__ == '__main__':
    TrackExtension().run()
