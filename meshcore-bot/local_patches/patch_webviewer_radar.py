#!/usr/bin/env python3
"""Source patch: a "Channel radar" page in the web viewer (see modules/channel_radar.py, templates/radar.html).

Runs after patch_webviewer_games.py (it anchors on the Games menu item). Adds a menu item right after Games,
GET /radar (the page) and GET /api/radar (read-only counts; no message content, nothing to change).
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
    "modules/web_viewer/app.py",
    """        @self.app.route('/region-warnings')
        def region_warnings_page():""",
    """        @self.app.route('/radar')
        def radar_page():
            \"\"\"Channel radar: which hashtag channels are in use around the bot (see modules/channel_radar.py).\"\"\"
            return render_template('radar.html')

        @self.app.route('/api/radar')
        def api_radar():
            \"\"\"Read-only counts per channel and day; no message content.\"\"\"
            import logging as _logging
            from types import SimpleNamespace
            from modules import channel_radar
            try:
                bot = SimpleNamespace(config=self.config, db_manager=self.db_manager, logger=self.logger or _logging.getLogger('radar'))
                return jsonify(channel_radar.summary(bot))
            except Exception as e:
                self.logger.error(f"Error in /api/radar: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/region-warnings')
        def region_warnings_page():""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-trophy"></i> Games
                        </a>
                    </li>
""",
    """                            <i class="fas fa-trophy"></i> Games
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/radar' }}" href="/radar">
                            <i class="fas fa-satellite-dish"></i> Channel radar
                        </a>
                    </li>
""",
)
