"""Shared rich consoles and the CLI's semantic color palette.

All human-readable CLI output goes through `console` (stdout) or
`err_console` (stderr). rich auto-disables styling when the stream is
not a TTY and honors the NO_COLOR environment variable, which is the
supported way to get plain output; machine output (--json) bypasses
these consoles entirely and is never styled.

Palette convention, applied across every command:
- passed / success: green
- failed: red
- errored / warnings: yellow
- file paths: cyan
- cluster names: magenta
- counts and headings: bold (headings bold purple)
- top-level "ERROR:" lines: bold red, on stderr

`soft_wrap=True` because a non-TTY Console otherwise wraps at 80
columns, which would corrupt long paths in piped/captured output.
`highlight=False` so rich's automatic number/path highlighting cannot
fight the semantic palette. Interpolated user data (paths, targets,
cluster names) must be styled via the `style=` kwarg or passed through
`rich.markup.escape`, never inlined into markup strings.
"""

from rich.console import Console

console = Console(soft_wrap=True, highlight=False)
err_console = Console(stderr=True, soft_wrap=True, highlight=False)
