"""Genera los scripts de autocompletado de yt-cli para bash, zsh y fish.

Typer usa su propio protocolo (`_YT_CLI_COMPLETE=complete_bash`, …), distinto
del de Click (`bash_complete`); escribir estos scripts a mano produjo en el
pasado completions que nunca completaban nada. Por eso se generan desde Typer:

    python packaging/generate_completions.py packaging/completions

El PKGBUILD lo ejecuta en build() y un test comprueba que los scripts
versionados coinciden con los generados.
"""

from __future__ import annotations

import sys
from pathlib import Path

from typer._completion_shared import get_completion_script

SHELLS = ("bash", "zsh", "fish")


def render(shell: str) -> str:
    script = get_completion_script(prog_name="yt-cli", complete_var="_YT_CLI_COMPLETE", shell=shell)
    return script.rstrip("\n") + "\n"


def main(output_dir: str) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    for shell in SHELLS:
        (target / f"yt-cli.{shell}").write_text(render(shell), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "packaging/completions")
