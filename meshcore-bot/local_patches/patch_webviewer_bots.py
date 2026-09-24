#!/usr/bin/env python3
"""Source patch: a "Bots" page in the web viewer (see modules/bots_admin.py, templates/bots.html).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Adds to the dashboard:
- a "Bots" item in the top navigation, right after Contacts;
- GET /bots (the page), GET /api/bots (every heard name with what the automatic rules make of it)
  and POST /api/bots/set (tick / untick / back to automatic, one name at a time).
The page edits the same hand-made lists as the admin command `botlist`, so both always agree.
The POST is covered by the viewer's existing login and X-Requested-With (CSRF) checks.
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
    """        @self.app.route('/bots')
        def bots_page():
            \"\"\"Bots: every heard name, tick who is a bot (see modules/bots_admin.py).\"\"\"
            return render_template('bots.html')

        @self.app.route('/api/bots')
        def api_bots():
            \"\"\"All heard names with the automatic verdict and any hand-made override.\"\"\"
            from modules import bots_admin
            try:
                return jsonify(bots_admin.list_names(self.db_manager, self.config, self.logger))
            except Exception as e:
                self.logger.error(f"Error in /api/bots: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/bots/set', methods=['POST'])
        def api_bots_set():
            \"\"\"Body: {"name": str, "is_bot": true | false | null} (null = back to automatic).\"\"\"
            from modules import bots_admin
            data = request.get_json(silent=True) or {}
            name = data.get('name')
            is_bot = data.get('is_bot')
            if not isinstance(name, str) or (is_bot is not None and not isinstance(is_bot, bool)):
                return jsonify({'error': 'name (string) and is_bot (true, false or null) are required'}), 400
            try:
                return jsonify(bots_admin.set_bot(self.db_manager, self.config, name, is_bot, self.logger))
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/bots/set: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/region-warnings')
        def region_warnings_page():""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-users"></i> Contacts
                        </a>
                    </li>
""",
    """                            <i class="fas fa-users"></i> Contacts
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/bots' }}" href="/bots">
                            <i class="fas fa-robot"></i> Bots
                        </a>
                    </li>
""",
)
