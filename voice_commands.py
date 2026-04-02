"""Voice command processor — matches transcribed text to command mappings.

Supports two action types in the 'shortcut' field of command mappings:
  - Keyboard shortcut: e.g. "ctrl+shift+alt+r" → executed via xdotool
  - Script path:       e.g. "script:talk.sh"   → runs scripts/<name> from SCRIPTS_DIR
"""

import logging
import os
import subprocess

import config

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


def is_script_action(shortcut):
    """Check if a shortcut value is a script action (prefixed with 'script:')."""
    return shortcut and shortcut.startswith("script:")


def _resolve_script_path(shortcut):
    """Resolve a 'script:name.sh' value to an absolute path in SCRIPTS_DIR."""
    script_name = shortcut[len("script:"):]
    return os.path.join(config.SCRIPTS_DIR, script_name)


def execute_script(shortcut):
    """Execute a script from the scripts/ directory.

    Args:
        shortcut: Action string like "script:talk.sh".
    """
    script_path = _resolve_script_path(shortcut)
    if not os.path.isfile(script_path):
        log.error("Script not found: %s", script_path)
        return
    if not os.access(script_path, os.X_OK):
        log.error("Script not executable: %s", script_path)
        return

    log.info("Executing script: %s", script_path)
    try:
        # Run script in background (Popen, not run) so it doesn't block
        subprocess.Popen(
            [script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process group
        )
    except OSError as exc:
        log.error("Failed to execute script %s: %s", script_path, exc)


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


def execute_action(shortcut):
    """Execute a command action — either a script or a keyboard shortcut.

    Args:
        shortcut: Either "script:name.sh" for scripts or a key combo for xdotool.
    """
    if not shortcut or shortcut == "__DICTATE__":
        return

    if is_script_action(shortcut):
        execute_script(shortcut)
    else:
        execute_shortcut(shortcut)
