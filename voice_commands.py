"""Voice command processor — matches transcribed text to command mappings."""

import logging
import subprocess

log = logging.getLogger("voice_commands")


def match_command(text, command_mappings):
    """Check if transcribed text matches any voice command phrase.

    Args:
        text: Transcribed text from whisper (after wake word activation).
        command_mappings: List of {"phrase": str, "shortcut": str} dicts.

    Returns:
        The matching mapping dict, or None if no match.
    """
    normalized = text.strip().lower()
    log.info("Matching command: %r against %d mappings", normalized, len(command_mappings))

    # Check for "dictate" command first (built-in)
    if normalized in ("dictate", "dictation", "start dictation", "start dictating"):
        log.info("Matched built-in DICTATE command")
        return {"phrase": "dictate", "shortcut": "__DICTATE__"}

    # Check user-defined command mappings
    for mapping in command_mappings:
        phrase = mapping.get("phrase", "").strip().lower()
        if phrase and phrase in normalized:
            log.info("Matched command: %r -> %s", phrase, mapping["shortcut"])
            return mapping

    log.info("No command matched for: %r", normalized)
    return None


def execute_shortcut(shortcut):
    """Execute a keyboard shortcut via xdotool.

    Args:
        shortcut: Key combination string (e.g., "ctrl+shift+alt+r").
    """
    if not shortcut or shortcut == "__DICTATE__":
        return

    cmd = ["xdotool", "key", "--clearmodifiers", shortcut]
    log.info("Executing shortcut: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, timeout=5, check=False, capture_output=True)
        if result.returncode != 0:
            log.error("xdotool failed (code %d): %s",
                      result.returncode,
                      result.stderr.decode(errors="replace"))
    except FileNotFoundError:
        log.error("xdotool not found")
    except subprocess.TimeoutExpired:
        log.error("xdotool timed out")
