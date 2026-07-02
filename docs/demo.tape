# vhs script: records `traceval demo` into docs/img/demo.gif.
# Regenerate with `make demo-gif` (requires vhs: brew install vhs).
# Target: <= 15s, showing the pipeline stages, the healthy PASS summary,
# and the buggy FAIL summary. Never hand-edit the GIF.

Output docs/img/demo.gif

Set FontSize 15
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms

Type "traceval demo -o /tmp/traceval-demo-gif --force"
Enter

# The pipeline stages print immediately; the two suite runs follow.
Sleep 9s

# Leave the closing summary (healthy PASSED, buggy FAILED) on screen.
Sleep 4s
