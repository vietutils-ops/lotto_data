# Updating the results, step by step

This guide is for whoever publishes new results to this repository. It uses
Windows and the Command Prompt; the macOS and Linux commands are in the note below.
Once the setup is done, an update takes a few minutes.

What an update does: the tool reads the newest results on vietlott.vn, checks
every draw, writes the files the app downloads, and you push them to GitHub.
Phones running LottoStat get the new results at their next check. Nothing
reaches the app until you push.

> macOS and Linux: activate the environment with `source .venv/bin/activate`,
> set a variable with `export NAME=value` instead of `set NAME=value`, and use
> your own folder instead of `C:\Workspace\Lotto_Data`.

## A. One-time setup

1. **Python 3.10 or newer.** In the Command Prompt, run `python --version`.
   If Windows answers that `python` is not recognized, install Python from
   python.org and tick *Add python.exe to PATH* in the installer.
2. **Git.** Run `git --version`. If it is missing, install Git for Windows
   (git-scm.com) with the default options. Then tell Git who you are (once):
   ```
   git config --global user.name "Your Name"
   git config --global user.email "the-email-of-your-github-account@example.com"
   ```
3. **The repository.** Skip this if you already have the folder:
   ```
   cd /d C:\Workspace
   git clone https://github.com/viettran88/lotto-data.git Lotto_Data
   ```
4. **The tools' environment**, a Python folder named `.venv` inside the
   repository (Git ignores it):
   ```
   cd /d C:\Workspace\Lotto_Data
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```
5. **Check that everything works:**
   ```
   python -m pytest -q
   python -m scripts.validate
   ```
   The tests end with `44 passed, 3 skipped` and the check prints `OK`. The
   skipped tests need saved copies of the source pages and a `vietlott-data`
   folder next to this one; skipping them is normal.
6. **Permission to push.** The first `git push` opens a browser window to sign
   in to GitHub. Sign in with an account that can write to the repository.

## B. When to update

* Mega 6/45 is drawn on Wednesday, Friday and Sunday, and Power 6/55 on
  Tuesday, Thursday and Saturday, in the evening, Vietnam time.
* Update after 20:00 Vietnam time on a draw day, or any time later. Running
  the tool before the results are out does no harm: it reports `up_to_date`.
* Not sure an update is due? `python -m scripts.health_check` shows
  `"stale": true` for a game when a draw from two or more days ago is missing.
* Update at least every five weeks. The tool reads the 18 newest results of
  each game; after a longer break, see `missing_draw_id` in part D.

## C. Each update

### Step 1. Open the folder and the environment

Open the Command Prompt (Start, type `cmd`, Enter) and run:

```
cd /d C:\Workspace\Lotto_Data
.venv\Scripts\activate
```

The prompt now starts with `(.venv)`. Run every following command in this
window.

### Step 2. Get the latest version of the repository

```
git pull
pip install -r requirements-dev.txt
```

`git pull` ends with `Already up to date.` or lists the files it updated.
`pip` installs something only when the tools' requirements changed. If
`git pull` says local changes would be overwritten, an earlier run was left
unfinished: see *Start again from a clean state* in part D.

### Step 3. Dry run: see what would change

```
python -m scripts.update --all
```

This writes nothing. For each game it prints a block like this one (an
example; your numbers will differ):

```json
{
  "game": "mega645",
  "dataset_version": "2026.10.18.001",
  "written": false,
  "rejected": 0,
  "added": 5,
  "added_first": "01573",
  "added_last": "01577",
  "changed": [],
  "removed": [],
  "unchanged": 1,
  "status": "changed"
}
```

* `status`: `changed` means new results were found, `up_to_date` means there
  is nothing new, and `failed` comes with an `error` code (see part D).
* `added`, `added_first` and `added_last`: how many new draws, from which draw
  number to which.
* `changed` and `removed` stay empty: the tool never alters a published draw
  on its own (it stops with `history_changed` instead).
* `rejected` should be `0`. It counts rows of the source page the tool could
  not read with certainty; they are never published. Mention a non-zero count
  when you ask for help.
* `dataset_version` is the version that will be published: today's date (UTC)
  and a counter.

If every game says `up_to_date`, stop here: there is nothing to publish.

### Step 4. Write the files

```
python -m scripts.update --all --write --run-tests
```

The same blocks appear, now with `"written": true`, then the tests run and end
with `44 passed, 3 skipped`. If the tests fail, do not commit: see part D.

For each game with new draws this updates `draws.json`, `metadata.json` and
`source.json` in its folder under `games\`, plus `catalog.json`,
`checksums\SHA256SUMS` and `metadata\audit_log.jsonl` (one new line per game).
Rejected rows, if any, are saved to a new file in `metadata\quarantine\`.

If one game failed and another was written, you can still publish the written
one (steps 5 and 6) and try the failed game again later.

### Step 5. Check and review

```
python -m scripts.validate
git status
```

* `validate` prints `OK`.
* `git status` lists only files under `catalog.json`, `checksums/`, `games/`
  and `metadata/`. If anything else changed, do not commit it.
* Look at the new draws with their numbers, and compare the newest one with
  vietlott.vn:
  ```
  git diff games/vn/vietlott_mega645/draws.json
  git diff games/vn/vietlott_power655/draws.json
  ```
  Each draw is one line, for example `{"draw_id": "01572", "draw_date":
  "2026-10-07", ..., "main_numbers": [10, 14, 36, 37, 41, 43], ...}`. Lines
  starting with `+` are new. Press `q` to leave the view.

### Step 6. Commit and push

```
git add catalog.json games checksums metadata
git commit -m "data: mega645 power655 update"
git push
```

Name only the games that changed in the message. `git push` ends with a line
like `main -> main`.

### Step 7. Check GitHub

Open <https://github.com/viettran88/lotto-data/actions>. The `validate` run of
your commit turns green within about a minute (one Linux and one Windows job).
If it turns red, ask for help with the link to the run.

### Step 8. Check the app

GitHub may take up to five minutes to serve the new files. Then, in the app,
tap the refresh button at the top of *Home*, or *More → Settings → Refresh
Data*. Without that, the app checks by itself when it starts, at most every
six hours.

* *Home → Latest result* shows the newest draw.
* *More → Data & sources* shows the latest draw and the dataset version from
  step 3.

### All commands in order

```
cd /d C:\Workspace\Lotto_Data
.venv\Scripts\activate
git pull
pip install -r requirements-dev.txt
python -m scripts.update --all
python -m scripts.update --all --write --run-tests
python -m scripts.validate
git status
git add catalog.json games checksums metadata
git commit -m "data: mega645 power655 update"
git push
```

## D. When something goes wrong

Nothing is published until you push, and a game that fails writes nothing.

| Code | What it means | What to do |
|---|---|---|
| `source_unavailable` | vietlott.vn could not be reached: no internet, the site is down, or it was too slow. | Check that vietlott.vn opens in your browser, then try again later. On a slow connection, run `set LOTTO_HTTP_TIMEOUT=60` first. |
| `access_denied` | The site refused the request or showed an "are you a robot" page. | The tool never tries to get around this, and neither should you. Wait a few hours and try once more; if it happens again, ask for help. |
| `robots_disallowed` | The site's `robots.txt` no longer allows these requests. | Stop and ask for help. Do not change the tool to get around it. |
| `rate_limited` | The site asked the tool to slow down. | Wait an hour. To be gentler, run `set LOTTO_RATE_LIMIT_DELAY=5` before trying again. |
| `parse_failed` | The site answered, but not in the format the tool knows; the site has probably changed. | Save the page with `python -m scripts.capture_fixture --game mega645` (or `power655`) and ask for help with the file it names and the output. Do not commit that file. |
| `no_data_found` | The site answered without any result. | As for `parse_failed`. |
| `data_invalid` | A result breaks the rules: wrong count of numbers, a date in the future, a missing draw number. | Nothing was written. If the message says `missing_draw_id` after a long break, repeat steps 3 and 4 with `--max-pages 10` added (each page holds 6 draws). Otherwise ask for help. |
| `history_changed` | The site shows different numbers for a draw already published, or a draw disappeared. | Nothing was written. Check that draw on vietlott.vn. Only if the official site really corrected it, repeat step 4 with `--accept-changes` added; the audit log records it. If unsure, ask for help. |
| `ruleset_unknown` | A draw date is not covered by the game's rules; Vietlott may have changed the game. | Stop and ask for help: the rules (`rulesets.json`) are edited by hand. |
| `schema_mismatch`, `checksum_failed` | A file was edited or damaged. | Start again from a clean state (below). |
| `distribution_restricted` | This game's data may not be published. | Nothing to do. |

Other problems:

* *`'python' is not recognized`*: see part A, step 1.
* *`No module named ...`* or *`ZoneInfoNotFoundError`*: the environment is not
  active or incomplete. Run `.venv\Scripts\activate`, then
  `pip install -r requirements-dev.txt`.
* *The tests fail after step 4*: do not commit. Ask for help with the output,
  then start again from a clean state.
* *`git push` is rejected* ("fetch first" or "non-fast-forward"): the
  repository on GitHub changed after your `git pull`. Start again from a clean
  state and repeat the update from step 2.
* *PowerShell refuses to run `activate`* ("running scripts is disabled"): use
  the Command Prompt, or run `Set-ExecutionPolicy -Scope CurrentUser
  RemoteSigned` once.

**Start again from a clean state.** This deletes every change in the folder
that you have not pushed, including a commit that failed to push; what is on
GitHub stays as it is. Your next update writes everything again from the
source.

```
git fetch origin
git reset --hard origin/main
git clean -fd games checksums metadata
```

**Asking for help.** Copy the whole output of the command that failed (select
it with the mouse, then press Ctrl+C), the output of `git status`, and say
which step you were at.

## E. Good to know

* Never edit `catalog.json` or the files in `games\`, `metadata\` and
  `checksums\` by hand, and do not open and save them in an editor: every byte
  is checked against its SHA-256, and an editor may change the line endings.
* The tool reads only what vietlott.vn shows every visitor, follows its
  `robots.txt`, waits at least a second between requests and never gets around
  a refusal. Do not run it in a loop.
* The app never goes back to an older dataset version. Do not undo a pushed
  update with `git revert` or a force push; correct a wrong draw with
  `--accept-changes` (part D), which publishes a newer version.
* Power 6/55 draw 00944 is missing on purpose and recorded in
  `config/known_gaps.json`. Nothing to do about it.
* The older repository `viettran88/vietlott-data` is read only by app builds
  made before the global version. If nobody uses such a build, it does not
  need updating.
* Updates can be automated later on a computer you control with the optional
  workflow `.github/workflows/collect.yml` (self-hosted runner).
