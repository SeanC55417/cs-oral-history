# Third-party libraries and datasets

This folder holds downloaded dependencies. The project's own Python code is in
`../ohcs/`; make normal project changes there. The local Python environment and
installed packages live in `../.venv/`.

| Folder | Source | Purpose |
|---|---|---|
| `medford/` | https://github.com/TuftsBCB/medford | Parses and validates MEDFORD metadata. This is the original `ext_medford/` checkout, moved here with its Git history intact. |
| `drafty/` | https://github.com/brownhci/drafty | Supplies the faculty sampling CSV. This checkout is not present yet. |

Only this guide is intended to be tracked in the main project repository. The
downloaded repositories are ignored by the root `.gitignore`; MEDFORD keeps its
own nested Git repository and license. Its existing tests and example datasets
belong to that dependency, not to the oral-history project.

The MEDFORD checkout present during organization was commit
`b8c380373f8cefcb344084f16cc0ca456ca25d87`. To restore it if this folder is absent,
run these commands from the project root:

```bash
git clone https://github.com/TuftsBCB/medford libraries/medford
git -C libraries/medford checkout b8c380373f8cefcb344084f16cc0ca456ca25d87
```

To obtain the missing faculty dataset:

```bash
git clone --depth 1 https://github.com/brownhci/drafty libraries/drafty
```

The sampler defaults to
`libraries/drafty/user_interest_profile/finalProfs.csv`. To use an existing CSV
elsewhere, export `DRAFTY_CSV` with its absolute path before running Python.
The exact Drafty revision used by the earlier sample is not recorded; a fresh
checkout may therefore contain different faculty rows.

After obtaining MEDFORD, install the project dependencies using
`python -m pip install -r requirements.txt` in the activated virtual environment.
