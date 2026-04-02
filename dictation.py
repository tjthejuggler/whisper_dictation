"""DictationManager — record/trim/transcribe/inject pipeline.

The recording itself is handled by AudioEngine (PyAudio).
This module manages the transcription pipeline: sox → whisper-cli → clipboard paste.
"""

import logging
import os
import subprocess
import time

from PyQt6.QtCore import QObject, QThread, pyqtSignal

import config

# ── Logging ────────────────────────────────────────────────────────
_LOG_PATH = "/tmp/vibe_debug.log"

log = logging.getLogger("dictation")
log.setLevel(logging.DEBUG)
log.propagate = False

_file_handler = None


def _reset_log_handler():
    """(Re-)create the file handler, truncating the log file."""
    global _file_handler
    if _file_handler is not None:
        log.removeHandler(_file_handler)
        _file_handler.close()
    _file_handler = logging.FileHandler(_LOG_PATH, mode="w")
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s")
    )
    log.addHandler(_file_handler)


# ── States ─────────────────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"
STATE_LISTENING = "listening"  # Wake word detected, waiting for command


# ── Transcription Worker (runs in QThread) ─────────────────────────
class TranscriptionWorker(QObject):
    """Runs sox → whisper-cli → clipboard paste in a background thread."""

    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, target_window_id=None):
        super().__init__()
        self._target_window_id = target_window_id

    def run(self):
        """Execute the full transcription pipeline with per-phase timing."""
        timings = {}
        pipeline_start = time.monotonic()
        try:
            t0 = time.monotonic()
            self._trim_silence()
            timings["audio_trim"] = time.monotonic() - t0

            t0 = time.monotonic()
            self._transcribe()
            timings["whisper"] = time.monotonic() - t0

            t0 = time.monotonic()
            text = self._read_output()
            timings["read_output"] = time.monotonic() - t0

            if text:
                t0 = time.monotonic()
                self._inject_text(text, self._target_window_id)
                timings["inject_text"] = time.monotonic() - t0
            else:
                log.info("No text to inject (empty transcription)")
                timings["inject_text"] = 0.0
        except Exception as exc:
            log.error("Pipeline error: %s", exc)
            self.error.emit(str(exc))
        finally:
            timings["total"] = time.monotonic() - pipeline_start
            self._log_timing_summary(timings)
            self._cleanup()
            self.finished.emit()

    @staticmethod
    def _log_timing_summary(timings):
        """Write a clear timing breakdown to the log."""
        log.info("=" * 50)
        log.info("TIMING BREAKDOWN")
        log.info("-" * 50)
        log.info("Audio processing time : %.3f seconds",
                 timings.get("audio_trim", 0))
        log.info("Whisper processing time: %.3f seconds",
                 timings.get("whisper", 0))
        log.info("Read output time       : %.3f seconds",
                 timings.get("read_output", 0))
        log.info("Typing/paste time      : %.3f seconds",
                 timings.get("inject_text", 0))
        log.info("Total pipeline time    : %.3f seconds",
                 timings.get("total", 0))
        log.info("=" * 50)

    def _trim_silence(self):
        """Strip leading/trailing silence with sox."""
        log.info("Trimming silence: %s", " ".join(config.SOX_CMD))
        result = subprocess.run(
            config.SOX_CMD,
            capture_output=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"sox failed (code {result.returncode}): {stderr}")
        # Check if trimmed file exists and has content
        if not os.path.isfile(config.TRIMMED_WAV):
            raise RuntimeError("sox produced no output file")
        size = os.path.getsize(config.TRIMMED_WAV)
        log.info("Trimmed WAV size: %d bytes", size)
        if size < 1000:  # WAV header is ~44 bytes; <1000 means essentially empty
            raise RuntimeError("Recording was all silence (nothing to transcribe)")

    def _transcribe(self):
        """Run whisper-cli on the trimmed audio."""
        cmd = [config.WHISPER_CLI_BIN] + config.WHISPER_ARGS
        log.info("Transcribing: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True, timeout=120, check=False,
        )
        log.info("whisper-cli returncode: %d", result.returncode)
        log.debug("whisper-cli stdout:\n%s",
                  result.stdout.decode(errors="replace"))
        stderr_text = result.stderr.decode(errors="replace")
        log.info("whisper-cli stderr (full):\n%s", stderr_text)
        if result.returncode != 0:
            raise RuntimeError(
                f"whisper-cli failed (code {result.returncode}): "
                f"{stderr_text.strip()[:200]}"
            )

    def _read_output(self):
        """Read transcribed text from the output file."""
        if not os.path.isfile(config.OUTPUT_TXT):
            log.warning("Output file not found: %s", config.OUTPUT_TXT)
            return ""
        with open(config.OUTPUT_TXT, "r", encoding="utf-8") as f:
            text = f.read().strip()
        log.info("Transcribed text (%d chars): %r", len(text), text[:200])
        return text

    @staticmethod
    def _inject_text(text, target_window_id=None):
        """Paste text into the target X11 window via clipboard (xsel + xdotool Ctrl+V)."""
        log.info("Injecting text via clipboard paste (%d chars)", len(text))
        try:
            # Copy text to clipboard using xsel
            t0 = time.monotonic()
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text.encode("utf-8"),
                timeout=5, check=True, capture_output=True,
            )
            log.info("Clipboard set via xsel (%.3f s)", time.monotonic() - t0)

            # Re-focus the target window so the paste lands in the right place
            if target_window_id:
                t0 = time.monotonic()
                subprocess.run(
                    ["xdotool", "windowactivate", "--sync", target_window_id],
                    timeout=3, check=False, capture_output=True,
                )
                log.info("Window re-focus (%.3f s)", time.monotonic() - t0)
                time.sleep(0.05)

            # Paste immediately
            if target_window_id:
                cmd = ["xdotool", "key", "--clearmodifiers",
                       "--window", target_window_id, "ctrl+v"]
            else:
                cmd = ["xdotool", "key", "--clearmodifiers", "ctrl+v"]
            log.info("Paste command: %s", " ".join(cmd))
            t0 = time.monotonic()
            result = subprocess.run(
                cmd, timeout=5, check=False, capture_output=True,
            )
            log.info("xdotool paste returncode: %d (%.3f s)",
                     result.returncode, time.monotonic() - t0)
            if result.returncode != 0:
                log.error("xdotool stderr: %s",
                         result.stderr.decode(errors="replace"))
        except FileNotFoundError as exc:
            log.error("Required tool not found: %s", exc)
        except subprocess.TimeoutExpired:
            log.error("Clipboard/paste timed out")
        except subprocess.CalledProcessError as exc:
            log.error("xsel failed: %s",
                     exc.stderr.decode(errors="replace") if exc.stderr else "unknown")

    @staticmethod
    def _cleanup():
        """Remove temp files."""
        for path in (config.RAW_WAV, config.TRIMMED_WAV, config.OUTPUT_TXT):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    log.debug("Removed: %s", path)
            except OSError as exc:
                log.warning("Failed to remove %s: %s", path, exc)


# ── Short Command Transcription Worker ─────────────────────────────
class CommandTranscriptionWorker(QObject):
    """Transcribes a short audio clip and returns the text (for voice commands)."""

    finished = pyqtSignal(str)  # emits the transcribed text
    error = pyqtSignal(str)

    def run(self):
        """Transcribe the recorded audio and emit the text."""
        try:
            # Trim silence
            result = subprocess.run(
                config.SOX_CMD,
                capture_output=True, timeout=30, check=False,
            )
            if result.returncode != 0:
                self.error.emit("sox failed")
                self.finished.emit("")
                return

            if not os.path.isfile(config.TRIMMED_WAV):
                self.finished.emit("")
                return

            if os.path.getsize(config.TRIMMED_WAV) < 1000:
                self.finished.emit("")
                return

            # Transcribe
            cmd = [config.WHISPER_CLI_BIN] + config.WHISPER_ARGS
            log.info("Command transcription: %s", " ".join(cmd))
            result = subprocess.run(
                cmd, capture_output=True, timeout=60, check=False,
            )
            if result.returncode != 0:
                self.error.emit("whisper-cli failed")
                self.finished.emit("")
                return

            # Read output
            if not os.path.isfile(config.OUTPUT_TXT):
                self.finished.emit("")
                return

            with open(config.OUTPUT_TXT, "r", encoding="utf-8") as f:
                text = f.read().strip()

            log.info("Command transcription result: %r", text)
            self.finished.emit(text)

        except Exception as exc:
            log.error("Command transcription error: %s", exc)
            self.error.emit(str(exc))
            self.finished.emit("")
        finally:
            # Clean up
            for path in (config.RAW_WAV, config.TRIMMED_WAV, config.OUTPUT_TXT):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass


def get_focused_window_id():
    """Get the currently focused X11 window ID."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, timeout=2, check=True,
        )
        wid = result.stdout.decode().strip()
        log.info("Captured focused window ID: %s", wid)
        return wid
    except Exception as exc:
        log.warning("Could not get focused window ID: %s", exc)
        return None


# ── Dictation Manager ─────────────────────────────────────────────
class DictationManager(QObject):
    """Manages the record → trim → transcribe → inject pipeline.

    Works with AudioEngine for recording instead of spawning arecord.
    """

    state_changed = pyqtSignal(str)     # "idle", "recording", "processing"
    error_occurred = pyqtSignal(str)

    def __init__(self, audio_engine, parent=None):
        super().__init__(parent)
        self._state = STATE_IDLE
        self._audio_engine = audio_engine
        self._worker = None
        self._thread = None
        self._target_window_id = None
        self._voice_triggered = False    # True if started via wake word

    @property
    def state(self):
        return self._state

    def toggle(self):
        """Handle tray icon click (Mode A: manual toggle)."""
        if self._state == STATE_IDLE:
            self._start_recording(voice_triggered=False)
        elif self._state == STATE_RECORDING:
            self._stop_and_process()
        # Ignore clicks during PROCESSING or LISTENING

    def start_voice_dictation(self):
        """Start dictation via voice command (Mode B: silence auto-stop)."""
        if self._state not in (STATE_IDLE, STATE_LISTENING):
            return
        self._start_recording(voice_triggered=True)

    def _start_recording(self, voice_triggered=False):
        """Begin recording via the audio engine."""
        _reset_log_handler()
        log.info("===== session starting (voice_triggered=%s) =====",
                 voice_triggered)

        self._voice_triggered = voice_triggered
        self._target_window_id = get_focused_window_id()

        # Clean up any leftover temp files
        for path in (config.RAW_WAV, config.TRIMMED_WAV, config.OUTPUT_TXT):
            if os.path.isfile(path):
                os.remove(path)

        # Start recording via audio engine
        self._audio_engine.start_recording(with_vad=voice_triggered)

        if voice_triggered:
            # Set up silence callback to auto-stop
            self._audio_engine.set_silence_callback(self._on_silence_timeout)

        self._state = STATE_RECORDING
        self.state_changed.emit(STATE_RECORDING)
        log.info("Recording started")

    def _on_silence_timeout(self):
        """Called by audio engine when silence timeout is reached (Mode B)."""
        log.info("Silence timeout — auto-stopping voice-triggered dictation")
        # This is called from the audio thread, so we need to be careful
        # The stop_and_process will be called, which handles thread safety
        self._stop_and_process()

    def _stop_and_process(self):
        """Stop recording and start the transcription pipeline."""
        if self._state != STATE_RECORDING:
            return

        # Stop recording in audio engine
        self._audio_engine.stop_recording()
        self._audio_engine.set_silence_callback(None)

        # Verify the WAV file was created
        if not os.path.isfile(config.RAW_WAV):
            log.error("No WAV file found after recording")
            self._state = STATE_IDLE
            self.state_changed.emit(STATE_IDLE)
            self.error_occurred.emit("Recording failed — no audio file produced.")
            return

        log.info("WAV file size: %d bytes", os.path.getsize(config.RAW_WAV))

        # Transition to processing state
        self._state = STATE_PROCESSING
        self.state_changed.emit(STATE_PROCESSING)

        # Start transcription in background thread
        self._thread = QThread()
        self._worker = TranscriptionWorker(
            target_window_id=self._target_window_id
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)

        self._thread.start()

    def _on_worker_finished(self):
        """Handle transcription pipeline completion."""
        log.info("===== session complete =====")
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
            self._thread = None
        self._worker = None
        self._target_window_id = None
        self._voice_triggered = False
        self._state = STATE_IDLE
        self.state_changed.emit(STATE_IDLE)

    def _on_worker_error(self, message):
        """Handle transcription pipeline error."""
        log.error("Worker error: %s", message)
        self.error_occurred.emit(message)

    def stop(self):
        """Force stop everything (for clean shutdown)."""
        self._audio_engine.stop_recording()
        self._audio_engine.set_silence_callback(None)

        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
            self._thread = None
        self._worker = None
        self._target_window_id = None
        self._voice_triggered = False
        self._state = STATE_IDLE
