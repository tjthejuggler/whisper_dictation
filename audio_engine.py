"""Unified audio engine — single PyAudio stream for wake word + recording."""

import logging
import struct
import threading
import time
import wave

import numpy as np
import pyaudio
import webrtcvad

import config

log = logging.getLogger("audio_engine")

# webrtcvad requires frames of 10, 20, or 30 ms at 16kHz
# 16000 * 0.030 = 480 samples per 30ms frame
_VAD_FRAME_SAMPLES = 480
_VAD_FRAME_BYTES = _VAD_FRAME_SAMPLES * config.AUDIO_FORMAT_WIDTH


class AudioEngine:
    """Manages a single continuous PyAudio mic stream.

    States:
        - idle: audio feeds into wake word detector
        - recording: audio is saved to WAV file
    """

    def __init__(self):
        self._pa = None
        self._stream = None
        self._running = False
        self._thread = None

        # Wake word
        self._oww_model = None
        self._wake_word_enabled = True
        self._wake_callback = None       # called when wake word detected
        self._wake_word_name = config.DEFAULT_WAKE_WORD  # model key for filtering
        self._custom_model_path = ""     # absolute path for custom .onnx models

        # Recording state
        self._recording = False
        self._wav_file = None
        self._wav_lock = threading.Lock()

        # VAD for silence detection (voice-triggered dictation)
        self._vad = webrtcvad.Vad(2)     # aggressiveness 0-3 (2 = balanced)
        self._silence_timeout = config.DEFAULT_SILENCE_TIMEOUT
        self._vad_enabled = False
        self._last_voice_time = 0.0
        self._silence_callback = None    # called when silence timeout exceeded

    def set_wake_callback(self, callback):
        """Set function to call when wake word is detected."""
        self._wake_callback = callback

    def set_silence_callback(self, callback):
        """Set function to call when silence timeout is exceeded during recording."""
        self._silence_callback = callback

    def set_silence_timeout(self, timeout):
        """Update the silence timeout (seconds)."""
        self._silence_timeout = timeout

    def set_wake_word_enabled(self, enabled):
        """Enable/disable wake word detection."""
        self._wake_word_enabled = enabled

    def start(self):
        """Open the mic stream and start the audio processing thread."""
        if self._running:
            return

        log.info("Starting audio engine")
        self._pa = pyaudio.PyAudio()

        # Use AUDIO_CHUNK that's a multiple of VAD frame size for clean processing
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=config.AUDIO_CHANNELS,
            rate=config.AUDIO_RATE,
            input=True,
            frames_per_buffer=config.AUDIO_CHUNK,
        )

        self._running = True
        self._thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._thread.start()
        log.info("Audio engine started")

        # Initialize wake word model (lazy load)
        self._init_wake_word()

    def stop(self):
        """Stop the audio stream and clean up."""
        log.info("Stopping audio engine")
        self._running = False

        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

        self.stop_recording()

        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

        log.info("Audio engine stopped")

    def start_recording(self, with_vad=False):
        """Begin saving audio to WAV file.

        Args:
            with_vad: If True, monitor for silence and auto-stop.
        """
        with self._wav_lock:
            if self._recording:
                return
            log.info("Starting recording (VAD=%s)", with_vad)
            self._wav_file = wave.open(config.RAW_WAV, "wb")
            self._wav_file.setnchannels(config.AUDIO_CHANNELS)
            self._wav_file.setsampwidth(config.AUDIO_FORMAT_WIDTH)
            self._wav_file.setframerate(config.AUDIO_RATE)
            self._recording = True
            self._vad_enabled = with_vad
            self._last_voice_time = time.monotonic()

    def stop_recording(self):
        """Stop recording and close the WAV file."""
        with self._wav_lock:
            if not self._recording:
                return
            log.info("Stopping recording")
            self._recording = False
            self._vad_enabled = False
            if self._wav_file is not None:
                try:
                    self._wav_file.close()
                except Exception:
                    pass
                self._wav_file = None

    @property
    def is_recording(self):
        return self._recording

    def set_wake_word_model(self, model_name, custom_path=""):
        """Change the active wake word model at runtime.

        Args:
            model_name: Model key from config.WAKE_WORD_MODELS values
                        (e.g. 'hey_jarvis_v0.1'), or config.CUSTOM_WAKE_WORD_KEY.
            custom_path: Absolute path to .onnx file (only used when
                         model_name == config.CUSTOM_WAKE_WORD_KEY).
        """
        if model_name == self._wake_word_name and custom_path == self._custom_model_path:
            return
        log.info("Switching wake word model: %s -> %s (custom=%s)",
                 self._wake_word_name, model_name, custom_path or "n/a")
        self._wake_word_name = model_name
        self._custom_model_path = custom_path
        # Reload model with the new wake word
        self._init_wake_word()

    def _init_wake_word(self):
        """Load the openwakeword model in a background thread."""
        model_name = self._wake_word_name
        custom_path = self._custom_model_path

        def _load():
            try:
                import openwakeword
                import os
                from openwakeword.model import Model

                if model_name == config.CUSTOM_WAKE_WORD_KEY:
                    # Custom user-provided .onnx file
                    model_path = custom_path
                else:
                    # Bundled model — resolve from openwakeword package
                    pkg_dir = os.path.dirname(openwakeword.__file__)
                    model_path = os.path.join(
                        pkg_dir, "resources", "models", f"{model_name}.onnx"
                    )

                if not model_path or not os.path.isfile(model_path):
                    log.error("Wake word model file not found: %s", model_path)
                    self._oww_model = None
                    return

                self._oww_model = Model(wakeword_model_paths=[model_path])
                # Store the actual prediction key for _check_wake_word
                keys = list(self._oww_model.models.keys())
                if keys:
                    self._wake_word_name = keys[0]
                log.info("Wake word model loaded: %s (keys=%s)",
                         model_path, keys)
            except Exception as exc:
                log.error("Failed to load wake word model: %s", exc)
                self._oww_model = None

        threading.Thread(target=_load, daemon=True).start()

    def _audio_loop(self):
        """Main audio processing loop — runs in a dedicated thread."""
        log.info("Audio loop started")
        while self._running:
            try:
                data = self._stream.read(config.AUDIO_CHUNK, exception_on_overflow=False)
            except Exception as exc:
                log.warning("Audio read error: %s", exc)
                time.sleep(0.01)
                continue

            # If recording, write to WAV and optionally check VAD
            if self._recording:
                with self._wav_lock:
                    if self._wav_file is not None:
                        self._wav_file.writeframes(data)

                if self._vad_enabled:
                    self._check_silence(data)
            else:
                # Idle — feed to wake word detector
                if self._wake_word_enabled and self._oww_model is not None:
                    self._check_wake_word(data)

        log.info("Audio loop ended")

    def _check_wake_word(self, data):
        """Feed audio chunk to openwakeword and check for detection."""
        try:
            # openwakeword expects int16 numpy array
            audio_array = np.frombuffer(data, dtype=np.int16)
            prediction = self._oww_model.predict(audio_array)

            # Only check the active wake word model
            target = self._wake_word_name
            score = prediction.get(target, 0.0)
            if score > config.WAKE_WORD_THRESHOLD:
                log.info("Wake word detected! model=%s score=%.3f",
                         target, score)
                # Reset the model to avoid repeated triggers
                self._oww_model.reset()
                if self._wake_callback:
                    self._wake_callback()
        except Exception as exc:
            log.debug("Wake word check error: %s", exc)

    def _check_silence(self, data):
        """Check if audio contains speech using webrtcvad."""
        try:
            # Process in 30ms frames as required by webrtcvad
            offset = 0
            has_voice = False
            while offset + _VAD_FRAME_BYTES <= len(data):
                frame = data[offset:offset + _VAD_FRAME_BYTES]
                if self._vad.is_speech(frame, config.AUDIO_RATE):
                    has_voice = True
                    break
                offset += _VAD_FRAME_BYTES

            now = time.monotonic()
            if has_voice:
                self._last_voice_time = now
            elif (now - self._last_voice_time) >= self._silence_timeout:
                log.info("Silence timeout reached (%.1fs)", self._silence_timeout)
                self._vad_enabled = False  # Prevent re-triggering
                if self._silence_callback:
                    self._silence_callback()
        except Exception as exc:
            log.debug("VAD check error: %s", exc)
