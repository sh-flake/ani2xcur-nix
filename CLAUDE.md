# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Toolkit for converting Windows ANI cursor themes to Linux XCursor format with NixOS overlay packaging. Written in Bash (orchestration) and Python 3 (core logic).

## Development Environment

```bash
nix develop          # Enter devShell with Python 3 + Pillow + NumPy
# Or: direnv allow   # Auto-activates via .envrc
```

Note: `win2xcur` (`pip install win2xcur`) is not provided by the devShell — install it separately. It provides the `win2xcurtheme` command used in the pipeline.

## Usage

```bash
# Full pipeline: resize ANI files → convert INF → win2xcurtheme → index.theme → Nix overlay
./make-cursor.sh <ThemeName>

# Individual tools
python ani-scale.py input.ani -o output.ani -s 32 -t 48
python inf-convert.py input.inf output.inf
```

There are no tests or linting configured.

## Architecture

Five-stage pipeline orchestrated by `make-cursor.sh`:

1. **ani-scale.py** — Resizes ANI cursor frames (e.g. 32→48px) using premultiplied alpha + Lanczos filtering. Parses/rebuilds RIFF/ANI binary format, handles multiple color depths (1/4/8/24/32 bpp), preserves hotspot coordinates.
2. **inf-convert.py** — Normalizes Windows `install.inf` files for `win2xcurtheme` compatibility (strips `[Wreg]`, standardizes rundll32 calls, fixes quoting/spacing, adds missing HKLM entries).
3. **win2xcurtheme** ([`win2xcur`](https://github.com/quantum5/win2xcur) 패키지) — Converts ANI → XCursor format.
4. Generates `index.theme` metadata file.
5. Creates a Nix overlay package file.

## Key Technical Details

- ANI files use RIFF container format with anih, rate, seq, and LIST/fram chunks
- Image resizing uses premultiplied alpha blending to avoid dark fringing on transparent edges
- INF parser handles section-based INI format with UTF-8 BOM support
- README is written in Korean
