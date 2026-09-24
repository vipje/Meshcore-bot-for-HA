#!/usr/bin/env python3
"""Source patch: a "Games" page in the web viewer (see modules/games_admin.py, templates/games.html).

Runs once during the Docker build, after patch_webviewer_bots.py (it anchors on the Bots menu item).

Adds to the dashboard:
- a "Games" item in the top navigation, right after Bots;
- GET /games (the page) and GET /api/games (read-only: Mesh RPG, DX Jacht, karma, check-in streaks, voorspel and
  the F1 prediction game, bots left out). Nothing on the page changes anything.
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
    """        @self.app.route('/games')
        def games_page():
            \"\"\"Games: standings of every game on the mesh (see modules/games_admin.py).\"\"\"
            return render_template('games.html')

        @self.app.route('/api/games')
        def api_games():
            \"\"\"Read-only standings, bots left out, no public keys.\"\"\"
            from modules import games_admin
            try:
                return jsonify(games_admin.standings(self.db_manager, self.config, self.logger))
            except Exception as e:
                self.logger.error(f"Error in /api/games: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/region-warnings')
        def region_warnings_page():""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-robot"></i> Bots
                        </a>
                    </li>
""",
    """                            <i class="fas fa-robot"></i> Bots
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/games' }}" href="/games">
                            <i class="fas fa-trophy"></i> Games
                        </a>
                    </li>
""",
)
