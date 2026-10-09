"""Render a command-only banner from the current recipe registry; never launch it."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from iwant.registry import list_models

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    for tool in ("vhs", "ffmpeg", "chromium", "ttyd"):
        if shutil.which(tool) is None:
            raise SystemExit(f"Missing {tool}; use the recording devcontainer.")
    models = list_models()
    if not models:
        raise SystemExit("No model recipes available.")
    first = "deepseek-v4-flash"
    if first in models:
        models.remove(first)
        models.insert(0, first)
    destination = ROOT / "docs" / "assets" / "banner.gif"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="iwant-banner-") as directory:
        temporary = Path(directory)
        video = temporary / "banner.mp4"
        palette = temporary / "palette.png"
        tape = temporary / "banner.tape"
        lines = [
            f'Output "{video}"',
            "Set Shell bash",
            'Set FontFamily "DejaVu Sans Mono"',
            "Set FontSize 46",
            "Set Width 1440",
            "Set Height 360",
            "Set Framerate 20",
            'Set Theme {"name":"iwant","background":"#101614","foreground":"#f1efe7",'
            '"cursor":"#8eecac","black":"#101614","brightBlack":"#101614",'
            '"green":"#8eecac","brightGreen":"#8eecac"}',
            "Set Padding 100",
            "Set Margin 0",
            "Set TypingSpeed 35ms",
            'Env PS1 "\\[\\e[38;2;142;236;172m\\]>\\[\\e[0m\\] "',
            'Env PROMPT_COMMAND ""',
            'Env HISTFILE "/dev/null"',
            "Hide",
            'Type "clear"',
            "Enter",
            "Wait+Line />$/",
            'Type "iwant up "',
            "Show",
            "Sleep 200ms",
        ]
        for model in models:
            lines.extend([f'Type "{model}"', "Sleep 1800ms"])
            lines.extend(["Backspace", "Sleep 15ms"] * len(model))
            lines.append("Sleep 200ms")
        tape.write_text("\n".join(lines) + "\n")
        # No Enter follows a launch command: the banner only types and deletes text.
        subprocess.run(["vhs", str(tape)], env={**os.environ, "VHS_NO_SANDBOX": "true"}, check=True)
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(video),
                "-vf",
                "fps=20,palettegen=stats_mode=diff",
                "-frames:v",
                "1",
                "-threads",
                "1",
                str(palette),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(video),
                "-i",
                str(palette),
                "-filter_complex",
                "[0:v]fps=20[video];[video][1:v]paletteuse=dither=bayer:bayer_scale=3",
                "-loop",
                "0",
                str(destination),
            ],
            check=True,
        )
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(destination), "-f", "null", "-"], check=True)
    print(f"Rendered {destination.relative_to(ROOT)} with {len(models)} available models.")


if __name__ == "__main__":
    main()
