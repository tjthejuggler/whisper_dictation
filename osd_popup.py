"""On-Screen Display popup — shows 'Listening...' when wake word detected."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import QLabel, QApplication, QGraphicsDropShadowEffect


class OSDPopup(QLabel):
    """Borderless, semi-transparent floating pill that shows status text."""

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

        # Style
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        self.setStyleSheet(
            "QLabel {"
            "  background-color: rgba(30, 30, 30, 200);"
            "  color: #00ff88;"
            "  border-radius: 20px;"
            "  padding: 12px 32px;"
            "}"
        )

        # Drop shadow for visibility
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def show_message(self, text="Listening..."):
        """Display the OSD at the top-center of the primary screen."""
        self.setText(text)
        self.adjustSize()

        # Position at top-center of primary screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 60  # 60px from top
            self.move(x, y)

        self.show()

    def hide_message(self):
        """Hide the OSD."""
        self.hide()
