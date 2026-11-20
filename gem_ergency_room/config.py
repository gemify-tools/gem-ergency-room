"""Runtime configuration: command-line flags override environment variables, which override defaults.

Environment variables
  GEM_HOST          bind address            (default 127.0.0.1; use 0.0.0.0 in containers)
  GEM_PORT / PORT   listen port             (default 8000)
  GEM_DB_PATH       SQLite database file    (default ./tasks.db)
  GEM_MAX_HIGH      Fire Drills cap         (default 3)
  GEM_MAX_MEDIUM    Important-ish cap       (default 5)
  GEM_MAX_LOW       Someday Maybe cap       (default unlimited)

A cap is a positive integer, or "unlimited" (also "none" / "0" / empty) for no cap.
"""
import argparse
import os

DEFAULT_LIMITS = {"High": 3, "Medium": 5, "Low": None}
UNLIMITED_WORDS = {"", "0", "none", "unlimited", "inf", "infinity"}
MAX_CAP = 10_000


def parse_cap(value, name="cap"):
    """Return a positive int, or None for unlimited."""
    if value is None:
        raise ValueError(f"{name}: no value")
    text = str(value).strip().lower()
    if text in UNLIMITED_WORDS:
        return None
    try:
        n = int(text)
    except ValueError:
        raise ValueError(f"{name}: {value!r} is not a whole number or 'unlimited'")
    if n < 0 or n > MAX_CAP:
        raise ValueError(f"{name}: must be between 1 and {MAX_CAP}, or 'unlimited'")
    return n or None


def _env(*names):
    for n in names:
        if n in os.environ:
            return os.environ[n]
    return None


class Config:
    def __init__(self, host="127.0.0.1", port=8000, db_path=None, limits=None):
        self.host = host
        self.port = port
        self.db_path = db_path or os.path.abspath("tasks.db")
        self.limits = dict(limits or DEFAULT_LIMITS)


def load(argv=None):
    p = argparse.ArgumentParser(
        prog="gem-ergency-room",
        description="The Gem-ergency Room: a tiny task board. Flags override GEM_* environment variables.",
    )
    p.add_argument("--host", help="bind address (env GEM_HOST, default 127.0.0.1)")
    p.add_argument("--port", type=int, help="listen port (env GEM_PORT or PORT, default 8000)")
    p.add_argument("--db", metavar="PATH", help="SQLite file (env GEM_DB_PATH, default ./tasks.db)")
    p.add_argument("--max-high", metavar="N", help="Fire Drills cap (env GEM_MAX_HIGH, default 3)")
    p.add_argument("--max-medium", metavar="N", help="Important-ish cap (env GEM_MAX_MEDIUM, default 5)")
    p.add_argument("--max-low", metavar="N", help="Someday Maybe cap (env GEM_MAX_LOW, default unlimited)")
    args = p.parse_args(argv)

    def pick(flag, *env_names):
        return flag if flag is not None else _env(*env_names)

    cfg = Config()
    try:
        cfg.host = pick(args.host, "GEM_HOST") or cfg.host
        port = pick(args.port, "GEM_PORT", "PORT")
        cfg.port = int(port) if port not in (None, "") else cfg.port
        if not 0 < cfg.port < 65536:
            raise ValueError("port: must be between 1 and 65535")
        cfg.db_path = os.path.abspath(pick(args.db, "GEM_DB_PATH") or cfg.db_path)
        for bucket, flag, env in (("High", args.max_high, "GEM_MAX_HIGH"),
                                  ("Medium", args.max_medium, "GEM_MAX_MEDIUM"),
                                  ("Low", args.max_low, "GEM_MAX_LOW")):
            raw = pick(flag, env)
            if raw is not None:
                cfg.limits[bucket] = parse_cap(raw, env)
    except ValueError as e:
        p.error(str(e))
    return cfg
