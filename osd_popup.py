"""On-Screen Display popup — shows 'Listening...' when wake word detected.

Old-timey silent-film aesthetic with voice-reactive avatar opacity.
Both avatar and text fade to nothing when silence timeout is reached.
"""

import os

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QLabel, QApplication, QGraphicsDropShadowEffect,
    QVBoxLayout, QGraphicsOpacityEffect,
)

# Resolve path to avatar image relative to this file
_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
_AVATAR_PATH = os.path.join(_ICON_DIR, "alkelly-head.png")


class OSDPopup(QWidget):
    """Borderless, semi-transparent floating panel that shows status text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # --- Text label wrapper (needed for opacity effect; label has drop shadow) ---
        self._label_wrapper = QWidget(self)
        self._label_wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        wrapper_layout = QVBoxLayout(self._label_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel(self._label_wrapper)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Serif font for that classic B&W movie title-card feel
        self._label.setFont(QFont("Georgia", 28, QFont.Weight.Bold))
        self._label.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(10, 10, 10, 210);"
            "  color: #e8e0d0;"
            "  border-radius: 16px;"
            "  padding: 14px 40px;"
            "  letter-spacing: 3px;"
            "}"
        )

        # Drop shadow for visibility
        shadow = QGraphicsDropShadowEffect(self._label)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 3)
        self._label.setGraphicsEffect(shadow)

        wrapper_layout.addWidget(self._label)

        # Opacity effect on the wrapper (so text + shadow fade together)
        self._label_opacity = QGraphicsOpacityEffect(self._label_wrapper)
        self._label_opacity.setOpacity(1.0)
        self._label_wrapper.setGraphicsEffect(self._label_opacity)

        # Animation for text fade
        self._label_anim = QPropertyAnimation(self._label_opacity, b"opacity")
        self._label_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        layout.addWidget(self._label_wrapper, alignment=Qt.AlignmentFlag.AlignHCenter)

        # --- Avatar image label (shown only during "Listening...") ---
        self._avatar = QLabel(self)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet("background: transparent;")
        if os.path.isfile(_AVATAR_PATH):
            pixmap = QPixmap(_AVATAR_PATH)
            # Scale image 3x larger
            pixmap = pixmap.scaled(
                pixmap.width() * 3, pixmap.height() * 3,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._avatar.setPixmap(pixmap)
        self._avatar.hide()

        # Opacity effect for voice-reactive animation
        self._opacity_effect = QGraphicsOpacityEffect(self._avatar)
        self._opacity_effect.setOpacity(0.25)
        self._avatar.setGraphicsEffect(self._opacity_effect)

        # Monitor avatar opacity to trigger text fade-out
        self._opacity_effect.opacityChanged.connect(self._on_avatar_opacity_changed)
        self._text_fading = False  # prevent re-triggering text fade

        # Voice-reactive animation: smoothly transitions between speech/silence
        self._voice_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._voice_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        layout.addWidget(self._avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

    def show_message(self, text="Listening..."):
        """Display the OSD at the top-center of the primary screen."""
        self._label.setText(text)
        self._label.adjustSize()

        # Show/hide avatar based on whether we're in "Listening..." state
        is_listening = (text == "Listening...")
        if is_listening:
            self._avatar.show()
            self._opacity_effect.setOpacity(0.25)
            self._label_opacity.setOpacity(1.0)
            self._label_anim.stop()
            self._text_fading = False
        else:
            self._voice_anim.stop()
            self._label_anim.stop()
            self._avatar.hide()
            self._label_opacity.setOpacity(1.0)
            self._text_fading = False

        self.adjustSize()

        # Position at top-center of primary screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 60  # 60px from top
            self.move(x, y)

        self.show()

    def on_voice_activity(self, has_voice):
        """React to VAD: boost opacity on speech, fade to zero on silence."""
        if not self._avatar.isVisible():
            return

        self._voice_anim.stop()
        current = self._opacity_effect.opacity()

        if has_voice:
            # Quickly boost toward 0.85
            target = 0.85
            duration = 200  # fast response
            # If text was fading, restore it instantly (match image speed)
            if self._text_fading or self._label_opacity.opacity() < 1.0:
                self._label_anim.stop()
                self._label_opacity.setOpacity(1.0)
                self._text_fading = False
        else:
            # Fade all the way to 0 (invisible)
            target = 0.0
            duration = 1500  # gentle fade

        # Skip if already close to target
        if abs(current - target) < 0.03:
            return

        self._voice_anim.setDuration(duration)
        self._voice_anim.setStartValue(current)
        self._voice_anim.setEndValue(target)
        self._voice_anim.start()

    def hide_message(self):
        """Hide the OSD and stop any running animation."""
        self._voice_anim.stop()
        self._label_anim.stop()
        self._text_fading = False
        self._avatar.hide()
        self.hide()

    def _on_avatar_opacity_changed(self, opacity):
        """When avatar gets very faint, rapidly fade the text label too."""
        if self._text_fading or opacity > 0.10:
            return
        # Avatar is at or below 10% — start rapid text fade
        self._text_fading = True
        current_text_opacity = self._label_opacity.opacity()
        if current_text_opacity <= 0.01:
            return
        self._label_anim.stop()
        self._label_anim.setDuration(300)  # rapid fade
        self._label_anim.setStartValue(current_text_opacity)
        self._label_anim.setEndValue(0.0)
        self._label_anim.start()
