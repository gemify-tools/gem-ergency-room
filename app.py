"""Standalone launcher: `python app.py` (no install needed). See README for flags and env vars."""
import os

# Keep the original behaviour: the database lives beside this file unless told otherwise.
os.environ.setdefault("GEM_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.db"))

from gem_ergency_room.server import main  # noqa: E402

if __name__ == "__main__":
    main()
