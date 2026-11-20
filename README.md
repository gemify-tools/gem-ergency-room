# The Gem-ergency Room

*A tiny task board for the work that is “quick” until it acquires three stakeholders and a steering committee.*

The Gem-ergency Room is a local, drag-and-drop task board. It sorts work into buckets that reflect the modern workplace’s nuanced relationship with urgency:

- **Fire Drills** (High): up to 3 tasks by default (configurable). The cap is a boundary, not a suggestion from leadership.
- **Important-ish** (Medium): up to 5 tasks by default (configurable). A comfortable place for work with a calendar invite.
- **Someday Maybe** (Low): unlimited. Optimism scales horizontally.
- **Done**: completed work, grouped by the date it was moved. The closest thing to a performance review this app provides.

Add a task with a description, stakeholder, soft deadline, and tags. Drag it between buckets, search active and completed work separately, expand cards for details, or double-click a card to edit it. Overdue tasks are marked “Late. Awkward.” Priorities follow the bucket when you move a task. The application runs on Python’s standard library and SQLite; there are no packages to install and no cloud account to align on.

## How to set it up

### Requirements

- Python 3.8 or newer
- A modern web browser

No virtual environment, package manager, or procurement ticket is required.

### Run it

From the project directory, start the server:

```bash
python app.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). The server listens on the local machine only. To use another port, set `PORT` before starting it:

```bash
# macOS / Linux
PORT=8080 python app.py

# Windows PowerShell
$env:PORT = "8080"
python app.py
```

Open `http://127.0.0.1:8080` when using the alternate port. Stop the server with `Ctrl+C`; the database will still be there, patiently awaiting the next check-in.

## Configuration

Every setting can be given as a command-line flag or an environment variable (flags win). Nothing is required.

| Flag | Environment variable | Default | Meaning |
|---|---|---|---|
| `--host` | `GEM_HOST` | `127.0.0.1` | Bind address |
| `--port` | `GEM_PORT` (or `PORT`) | `8000` | Listen port |
| `--db` | `GEM_DB_PATH` | `tasks.db` (beside `app.py` when run that way; otherwise the current directory) | SQLite file |
| `--max-high` | `GEM_MAX_HIGH` | `3` | Fire Drills cap |
| `--max-medium` | `GEM_MAX_MEDIUM` | `5` | Important-ish cap |
| `--max-low` | `GEM_MAX_LOW` | `unlimited` | Someday Maybe cap |

A cap is a whole number from 1 to 10000, or `unlimited` (also `none`, `0`). Lowering a cap below the current count keeps existing tasks but blocks new ones until the bucket drains. Done has no cap.

## Ways to run it

```bash
# 1. Standalone, no install (Python 3.8+)
python app.py --max-high 2 --max-medium 8

# 2. Installed as a command (pip or pipx)
pipx install .          # or: pip install .
gem-ergency-room --port 8080 --db ~/gem/tasks.db     # also: python -m gem_ergency_room

# 3. Docker
docker build -t gem-ergency-room .
docker run -p 127.0.0.1:8000:8000 -v gem-data:/data -e GEM_MAX_HIGH=2 gem-ergency-room

# 4. Docker Compose (data persists in the gem-data volume; caps come from GEM_MAX_* in your shell or a .env file)
docker compose up -d
```

`deploy/gem-ergency-room.service` is an example systemd unit for a Linux host. `GET /healthz` is available for container and load-balancer health checks.

**Security:** the app has no authentication. The container binds `0.0.0.0` internally, but the examples publish it on `127.0.0.1` only. To share it on a network, put an authenticating reverse proxy in front of it.

## Exporting completed tasks

The Done column has **CSV / JSON / PDF** links. They call `GET /api/export?format=csv|json|pdf`, with optional `from=YYYY-MM-DD` and `to=YYYY-MM-DD` to filter by completion date:

```bash
curl -o done.csv "http://127.0.0.1:8000/api/export?format=csv&from=2026-10-01"
```

Each record has ID, name, description, stakeholder, due date, last priority, tags, created time, completed time, and whether it was completed after its due date. Tasks created before this version have no created time. CSV cells that begin with `=`, `+`, `-` or `@` are prefixed with `'` so spreadsheets do not execute them. The PDF is generated without any third-party library; characters outside Windows-1252 (e.g. CJK) are replaced with `?` in the PDF only.

## Color schemes

The dropdown in the header switches between five schemes: **Calm blue** (default), Stormy morning, Urban graffiti, Harbor haze and Desert mirage. They follow the color descriptions of the same-named entries in [Figma's color combinations library](https://www.figma.com/resource-library/color-combinations/); that page publishes palette images without hex codes, so the exact values are our own interpretation. The choice is remembered in your browser.

## Sample configuration/setup and screenshots of usage

There is no configuration file; see Configuration above. On first launch, the app creates `tasks.db` beside `app.py`.

### A sample day at the office

1. Start the app and choose **Align** to add a task.
2. Enter **“Get Q4 numbers from Finance”**, description **“Need the final forecast before the deck goes to leadership.”**, stakeholder **“Finance”**, and a due date. Add tags such as `q4` and `forecast`.
3. Put a genuine fire in **Fire Drills**, a likely deliverable in **Important-ish**, or a distant aspiration in **Someday Maybe**. Fire Drills tops out at 3; Important-ish at 5. The app politely suggests descoping when a capped bucket is full.
4. Drag the card as work changes status. Move completed work to **Done**; it will be filed under today’s date, where the win can enjoy appropriate visibility.
5. Search active tasks or Done using their separate search boxes. Search checks task name, description, stakeholder, due date, and tags.

### Screenshots

The screenshot below shows the running board with active tasks, bucket capacity indicators, search, and a dated **Done** item. Expand any card to see its description and full tag list; double-click it to edit.

![The Gem-ergency Room task board with active and completed tasks](screenshots/capture.png)

## Technical notes

- `gem_ergency_room/server.py` serves both the page and a small JSON API using Python’s built-in HTTP server (`app.py` is a thin launcher). `index.html` contains the browser interface; `icon.svg` is the app icon; `export.py` and `config.py` handle exports and settings.
- Tasks are stored in `tasks.db` (SQLite), created automatically on first run. The database is local and is ignored by Git. Back it up by stopping the app and copying that file; deleting it removes the task data.
- By default the server binds to `127.0.0.1`, so it is intended for use on the same computer, not as a public or shared network service.
- The configured caps are enforced by the server, including during drag-and-drop. Low and Done have no cap. A task moved back out of Done retains its previous priority only until moved into another active bucket, where priority matches the destination.
- Text fields are trimmed and validated. Names and stakeholder fields allow up to 200 characters; descriptions up to 5,000; due dates use `YYYY-MM-DD`; each task can have up to 10 tags, each up to 30 characters.
- The API routes are `GET /api/tasks`, `POST /api/tasks`, `PUT /api/tasks/<id>`, `DELETE /api/tasks/<id>`, `POST /api/move`, `GET /api/config`, `GET /api/export` and `GET /healthz`.
- The database initializer adds the tags column to an older database if needed.

## Troubleshooting

- **The page does not open:** confirm the terminal still shows the server running and use the matching port. If port 8000 is occupied, choose another with `PORT`.
- **A task did not move:** check whether the destination’s High or Medium bucket is already at capacity. Some work requires descoping; the database has no executive override.
- **Tasks disappeared:** confirm you are running the same copy of the project. Each copy stores its own `tasks.db` beside its `app.py`.

## License

No license is specified in this repository. Please check with the project owner before redistributing it; even synergy has boundaries.
