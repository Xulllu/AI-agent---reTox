# reTox

**reTox** is a tool for moderating comments on Reddit. The application works as a **multi-agent system** (Sense → Think → Act → Learn) that:

* collects comments from Reddit posts (scrape job),
* automatically evaluates toxicity,
* sends suspicious comments for moderation,
* uses moderator decisions (gold labels) to retrain the model.

## Features

* UI pages: Home, Dashboard, Moderation, Admin
* 3 background agents (workers):

  * Collection agent: collects comments
  * Classification agent: classifies comments (toxicity + confidence + context)
  * Learning agent: tracks gold labels and triggers retraining
* SQLite database (WAL + busy_timeout) for more stable multi-process operation
* Observability: agent events available via `/health` and `/api/agents/events`
* Training:

  * automatic (when a threshold is reached),
  * manual (Admin → Train Model)
* Dataset import (optional): `ruddit_comments_score.csv`

---

## Project Structure (short)

* [run.py](run.py) – starts Flask API + 3 worker processes
* [web/app.py](web/app.py) – Flask routes + API
* [web/templates/](web/templates/) – HTML UI (dashboard/moderation/admin/home)
* [application/runners/](application/runners/) – CollectionRunner / ClassificationRunner / LearningRunner
* [core/software_agent.py](core/software_agent.py) – agent base (Sense/Think/Act) + event tracing
* [infrastructure/database.py](infrastructure/database.py) – SQLite layer, schema, queries, WAL settings

---

## Setup (Windows 10/11)

### 0) Prerequisites (Python 3.11.x)

This project uses `torch==2.2.2` (via `detoxify`), so it is most stable with **Python 3.11.x**.
On newer PCs, Python 3.12 is often installed automatically, but Torch installation may fail in that case.

Check which Python versions you have:

```powershell
py --list
# or:
py -0p
```

Install Python 3.11 if needed:

```powershell
winget install -e --id Python.Python.3.11
```

---

### 1) Install + run (Python 3.11 recommended)

In the `retox_` project folder:

```powershell
cd retox_

# Create a virtual environment with Python 3.11
py -3.11 -m venv .venv

# If you don’t have the py launcher, you can use:
# python --version
# python -m venv .venv

.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

python -m spacy download en_core_web_sm
```

If you get HTTP 404 / download failure, install directly (tar.gz):

```powershell
python -m pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1.tar.gz
```

# (alternative, often most stable: wheel)

```powershell
# python -m pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl
```

```powershell
python run.py
```
