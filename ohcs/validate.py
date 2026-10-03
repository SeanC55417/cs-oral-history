"""Validate one .mfd with the official TuftsBCB MEDFORD parser and print every error in detail.

    python -m ohcs.validate out/medford/x.mfd          (run once per file: parser state is global)
Exit code 0 = no errors, 2 = only 'desirable' warnings, 1 = real errors.
"""
import contextlib
import io
import os
import sys
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"


def main(path: str) -> int:
    # Resolve the input before switching to the folder containing our schema.
    path = str(Path(path).resolve())
    os.chdir(SCHEMA_DIR)                      # parser loads type rules from ./medford.yaml
    sys.argv = ["medford", "validate", path]  # Supply arguments to the library's CLI.
    import MEDFORD
    import MEDFORD.mfdglobals as g
    # Capture parser messages so we can print them and classify the outcome.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            MEDFORD.parse_args_and_go()
        except SystemExit:
            # Let this wrapper choose the exit code after inspecting diagnostics.
            pass
        g.mv.instance().print_other_errs()
    out = buf.getvalue()
    # Separate field diagnostics from the parser's general progress messages.
    errs = [l for l in out.splitlines() if l.startswith("line ") or "rror" in l and "errors found" not in l.lower()]
    type_fail = "All validations passed" not in out
    desirable_only = errs and all("desirable" in e for e in errs)
    print(out.strip())
    if not errs and not type_fail:
        return 0
    return 2 if desirable_only and not type_fail else 1  # Warnings versus errors.


if __name__ == "__main__":
    # Return the validation result to the shell or the sample runner.
    sys.exit(main(sys.argv[1]))
