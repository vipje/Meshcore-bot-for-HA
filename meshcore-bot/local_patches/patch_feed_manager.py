#!/usr/bin/env python3
"""Source patch applied to the vendored meshcore-bot feed manager.

Runs once during the Docker build, right after `git clone` (see
patch_webviewer.py for the shared rationale/mechanics).

FeedManager has no recency cutoff of its own: the first time a feed is
checked, every item currently in it is "new" (nothing has been seen yet),
so it gets queued and sent - all of it, as fast as the send-rate limiter
allows. That's exactly what happened activating the p2000 (P2000
Zuid-Limburg) feed: ~20-30 backlog items queued at once and trickled out
against repeated "Rate limited" retries. A per-feed `filter_config` with a
`within_days` condition could do this already, but there's no chat command
to set it (only creatable via the web viewer), so this adds a global
baseline instead: `[Feed_Manager] default_max_item_age_minutes` skips
queuing any item older than that, for every feed, independent of whichever
per-feed filter_config (if any) is also configured. 0 keeps upstream's
original unfiltered behavior.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


patch(
    "modules/feed_manager.py",
    "            self.rate_limit_seconds = bot.config.getfloat('Feed_Manager', 'feed_rate_limit_seconds', fallback=5.0)\n",
    "            self.rate_limit_seconds = bot.config.getfloat('Feed_Manager', 'feed_rate_limit_seconds', fallback=5.0)\n"
    "            self.default_max_item_age_minutes = bot.config.getfloat('Feed_Manager', 'default_max_item_age_minutes', fallback=0.0)\n",
)

patch(
    "modules/feed_manager.py",
    '''    def _should_send_item(self, feed: dict[str, Any], item: dict[str, Any]) -> bool:
        """Check if an item should be sent based on filter configuration.

        See modules/feed_filter_eval.py and docs/FEEDS.md for operators.
        """
        def _warn(msg: str) -> None:
            self.logger.warning(f"{msg} (feed id {feed.get('id')})")

        return item_passes_filter_config(
            item,
            feed.get('filter_config'),
            log_warning=_warn,
        )''',
    '''    def _should_send_item(self, feed: dict[str, Any], item: dict[str, Any]) -> bool:
        """Check if an item should be sent based on filter configuration.

        See modules/feed_filter_eval.py and docs/FEEDS.md for operators.
        """
        def _warn(msg: str) -> None:
            self.logger.warning(f"{msg} (feed id {feed.get('id')})")

        if not item_passes_filter_config(
            item,
            feed.get('filter_config'),
            log_warning=_warn,
        ):
            return False

        if self.default_max_item_age_minutes > 0:
            published = item.get('published')
            if published is not None:
                age_seconds = (datetime.now(timezone.utc) - published).total_seconds()
                if age_seconds > self.default_max_item_age_minutes * 60:
                    return False

        return True''',
)
