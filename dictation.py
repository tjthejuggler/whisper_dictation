"""DictationManager — record/trim/transcribe/inject pipeline."""

import logging
import os
import signal
import subprocess

from PyQt5.QtCore import QObject, QThread, pyqtSignal

import config

# ── Logging ────────────────────────────────────────────────────────
_LOG_PATH = "/tmp/dictation_debug.log"

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


# ── Transcription Worker (runs in QThread) ─────────────────────────
class TranscriptionWorker(QObject):
    """Runs sox → whisper-cli → xdotool in a background thread."""

    finished = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        """Execute the full transcription pipeline."""
        try:
            self._trim_silence()
            self._transcribe()
            text = self._read_output()
            if text:
                self._inject_text(text)
            else:
                log.info("No text to inject (empty transcription)")
        except Exception as exc:
            log.error("Pipeline error: %s", exc)
            self.error.emit(str(exc))
        finally:
            self._cleanup()
            self.finished.emit()

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
        log.debug("whisper-cli stdout: %s",
                  result.stdout.decode(errors="replace")[:500])
        log.debug("whisper-cli stderr: %s",
                  result.stderr.decode(errors="replace")[:500])
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(
                f"whisper-cli failed (code {result.returncode}): {stderr[:200]}"
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
    def _inject_text(text):
        """Type text into the active X11 window using xdotool."""
        log.info("Injecting text via xdotool (%d chars)", len(text))
        try:
            result = subprocess.run(
                ["xdotool", "type", "--clearmodifiers", "--delay", "2", "--", text],
                timeout=30, check=False, capture_output=True,
            )
            log.info("xdotool returncode: %d", result.returncode)
            if result.returncode != 0:
                log.error("xdotool stderr: %s",
                         result.stderr.decode(errors="replace"))
        except FileNotFoundError:
            log.error("xdotool not found!")
        except subprocess.TimeoutExpired:
            log.error("xdotool timed out")

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


# ── Dictation Manager ─────────────────────────────────────────────
class DictationManager(QObject):
    """Manages the record → trim → transcribe → inject pipeline."""

    state_changed = pyqtSignal(str)     # "idle", "recording", "processing"
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = STATE_IDLE
        self._arecord_proc = None
        self._worker = None
        self._thread = None

    @property
    def state(self):
        return self._state

    def toggle(self):
        """Handle tray icon click."""
        if self._state == STATE_IDLE:
            self._start_recording()
        elif self._state == STATE_RECORDING:
            self._stop_and_process()
        # Ignore clicks during PROCESSING

    def _start_recording(self):
        """Launch arecord to capture microphone input."""
        _reset_log_handler()
        log.info("===== session starting =====")

        # Clean up any leftover temp files
        for path in (config.RAW_WAV, config.TRIMMED_WAV, config.OUTPUT_TXT):
            if os.path.isfile(path):
                os.remove(path)

        log.info("Starting arecord: %s", " ".join(config.ARECORD_CMD))
        try:
            self._arecord_proc = subprocess.Popen(
                config.ARECORD_CMD,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            self.error_occurred.emit(
                "arecord not found. Install with: sudo apt install alsa-utils"
            )
            return
        except OSError as exc:
            self.error_occurred.emit(f"Failed to start arecord: {exc}")
            return

        log.info("arecord started (PID %d)", self._arecord_proc.pid)
        self._state = STATE_RECORDING
        self.state_changed.emit(STATE_RECORDING)

    def _stop_and_process(self):
        """Stop arecord and start the transcription pipeline."""
        if self._arecord_proc is None:
            return

        pid = self._arecord_proc.pid
        log.info("Stopping arecord (PID %d)", pid)

        # Send SIGTERM to finalize the WAV file
        try:
            os.kill(pid, signal.SIGTERM)
            self._arecord_proc.wait(timeout=5)
        except ProcessLookupError:
            log.warning("arecord already exited")
        except subprocess.TimeoutExpired:
            log.warning("arecord didn't stop in 5s, sending SIGKILL")
            self._arecord_proc.kill()
            self._arecord_proc.wait(timeout=3)

        self._arecord_proc = None

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
        self._worker = TranscriptionWorker()
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
        self._state = STATE_IDLE
        self.state_changed.emit(STATE_IDLE)

    def _on_worker_error(self, message):
        """Handle transcription pipeline error."""
        log.error("Worker error: %s", message)
        self.error_occurred.emit(message)

    def stop(self):
        """Force stop everything (for clean shutdown)."""
        if self._arecord_proc is not None:
            try:
                self._arecord_proc.terminate()
                self._arecord_proc.wait(timeout=3)
            except Exception:
                pass
            self._arecord_proc = None

        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
            self._thread = None
        self._worker = None
        self._state = STATE_IDLE
