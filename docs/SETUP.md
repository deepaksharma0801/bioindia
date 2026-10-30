# Running BioIndia on a new computer

This sets up the full platform: the database, the API and the dashboard, with all the data already
loaded. It takes about 20 minutes, most of it downloads. You do not need Python or any database skills;
Docker runs everything.

Just want to look at it? The hosted dashboard needs no setup:
https://deepaksharma0801.github.io/bioindia/

## What you need

- **Git**: https://git-scm.com/downloads
- **Docker Desktop**: https://www.docker.com/products/docker-desktop/ (on Windows, accept the WSL 2
  option during install and restart if asked)
- **`bioindia_data_bundle.zip`** (1.3 GB), sent to you separately. It is not on GitHub because of its
  size and licences (see [Data licences](#data-licences)).
- About **8 GB of free disk space**

Open Docker Desktop and wait until it says it is running before you start.

## Setup

Commands are for **PowerShell on Windows**. Mac and Linux differences are noted. Run them one at a time.

**1. Get the code**

```powershell
git clone https://github.com/deepaksharma0801/bioindia.git
```

```powershell
cd bioindia
```

**2. Unzip the data bundle into that folder.** Use the path to where you saved the zip:

```powershell
Expand-Archive -Path "$HOME\Downloads\bioindia_data_bundle.zip" -DestinationPath . -Force
```

On Mac or Linux: `unzip ~/Downloads/bioindia_data_bundle.zip`

You should now see `bioindia.dump` and a `data` folder inside `bioindia`.

**3. Start the database**

```powershell
docker compose up -d postgis
```

Wait about 15 seconds, then copy the data into it:

```powershell
docker cp bioindia.dump bioindia-postgis:/tmp/bioindia.dump
```

**4. Load the data** (about 1 to 5 minutes)

```powershell
docker exec bioindia-postgis pg_restore -U bioindia -d bioindia --no-owner -j 2 /tmp/bioindia.dump
```

It finishes with `errors ignored on restore: 3` and a few `already exists` messages. **That is expected
and harmless.** Check the data arrived:

```powershell
docker exec bioindia-postgis psql -U bioindia -d bioindia -c "SELECT count(*) FROM occurrences"
```

This should show **1398890**.

**5. Start the app** (the first run takes a few minutes while it builds)

```powershell
docker compose --profile app up -d --build
```

**6. Open it:** http://localhost:8080

Give the page a few seconds to load its data. The badge in the corner should read **"Live data: GBIF
occurrences (PostGIS)"**. API documentation is at http://localhost:8080/docs.

You can now delete `bioindia.dump` and the zip to save space.

## Everyday use

Docker Desktop must be running. From the `bioindia` folder:

| To | Run |
|---|---|
| Stop the app (your data is kept) | `docker compose --profile app stop` |
| Start it again | `docker compose --profile app start` |
| Get the latest code | `git pull`, then `docker compose --profile app up -d --build` |

## If something goes wrong

| What you see | What to do |
|---|---|
| `failed to connect to the docker API` or `cannot find the file specified` | Docker Desktop is not running. Open it, wait until it is ready, try again. |
| `port is already allocated` | Something else is using port 5432, 8000 or 8080, often another PostgreSQL. Stop it, then rerun the command. |
| `dependency failed to start` during step 5 | Usually a brief Docker hiccup. Run the same command again. |
| `could not connect to server` in step 3 or 4 | The database is still starting. Wait 30 seconds and retry. |
| The page shows "Demo" labels or empty sections | The API is not ready. Wait 30 seconds and refresh. Check `docker compose --profile app ps` shows `bioindia-api` as `healthy`. |
| Something still looks wrong | Run `docker logs bioindia-api` and send the last lines to the project owner. |

To start again from nothing (this deletes the loaded database), run
`docker compose --profile app down -v` and repeat from step 3.

## For developers (optional)

Everything above works without Python. To run the tests or change the code, install Python 3.12 or newer, then:

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
```

```powershell
.\.venv\Scripts\python.exe -m pytest -q scripts/tests
```

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest -q; cd ..
```

On Mac or Linux use `.venv/bin/python`. The backend tests use the database, so it must be running.
Rebuilding all the data from the original sources is a separate, much longer job: see the
[README](../README.md) and `scripts/run_pipeline.py`.

The bundle itself is made with `python scripts/make_data_bundle.py`.

## Data licences

The bundle includes data derived from the IUCN Red List and WDPA, whose terms allow non-commercial
research use but restrict redistribution. **Keep the bundle private: do not post it publicly, upload it
to a public link, or commit it to git.** GBIF data is cited as GBIF.org (2026),
https://doi.org/10.15468/dl.dvgq2s, and carries CC BY-NC terms as a combined download.
