"""
Ultron Assistant — Interface Gráfica
=====================================
Janela frameless, always-on-top, arrastável.
Orb central animado com 4 estados:
  idle        → pulso vermelho suave (2s)
  listening   → reage à amplitude do microfone
  processing  → 3 anéis giratórios + linha de scan
  speaking    → ondas de ripple expansivas

Comunicação thread-safe: fila ui_queue alimentada pelo loop assíncrono.
"""
import math
import queue
import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import (
    QColor, QPainter, QRadialGradient, QLinearGradient,
    QPen, QBrush, QFont, QPainterPath,
)
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication

# ── Fila global thread-safe para comunicação backend → UI ────────────────────
ui_queue: queue.Queue = queue.Queue()

# ── Paleta Ultron ────────────────────────────────────────────────────────────
_RED_CORE  = QColor(255,  55,  15)
_RED_MID   = QColor(220,  20,   0)
_RED_GLOW  = QColor(255,  10,   0)
_ORG_RING  = QColor(255, 110,  30)
_DIM_RING  = QColor(180,  15,   0)
_TEXT_COL  = QColor(255,  90,  60)
_BG_COL    = QColor(  6,   0,   1, 215)   # quase preto, levemente translúcido
_BORDER    = QColor(160,  15,   0, 100)


# ─────────────────────────────────────────────────────────────────────────────
#  OrbWidget — o coração animado
# ─────────────────────────────────────────────────────────────────────────────

class OrbWidget(QWidget):
    SIZE = 240       # px da área do widget
    ORB_R = 52       # raio base do orbe central

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.state: str = "idle"
        self.amplitude: float = 0.0   # 0–1
        self.t: float = 0.0
        self._intensity: float = 0.4  # intensidade suavizada
        self._last = time.perf_counter()

        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(16)   # ~60 fps

    def set_state(self, s: str):
        self.state = s

    def set_amplitude(self, a: float):
        self.amplitude = max(0.0, min(1.0, a))

    def _tick(self):
        now = time.perf_counter()
        self.t += now - self._last
        self._last = now
        self.update()

    # ── paintEvent ────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = self.SIZE / 2
        t = self.t

        if   self.state == "idle":        self._idle(p, cx, cy, t)
        elif self.state == "listening":   self._listening(p, cx, cy, t)
        elif self.state == "processing":  self._processing(p, cx, cy, t)
        elif self.state == "speaking":    self._speaking(p, cx, cy, t)
        p.end()

    # ── Estados ───────────────────────────────────────────────────────────────

    def _idle(self, p, cx, cy, t):
        b = 0.97 + 0.03 * math.sin(t * math.pi)       # respiração 2s
        self._glow(p, cx, cy, 0.30 * b)
        self._ring(p, cx, cy, r=68, w=0.7, spd=6,  ph=t, arc=160, col=QColor(150, 12, 0, 50))
        self._core(p, cx, cy, scale=b, intensity=0.55)

    def _listening(self, p, cx, cy, t):
        amp = self.amplitude
        react = 1.0 + amp * 0.22
        ity   = 0.55 + amp * 0.45

        self._glow(p, cx, cy, ity * react)
        self._ring(p, cx, cy, r=72,  w=1.2, spd=30, ph=t,       arc=200, col=QColor(255, 55, 0, int(130 * ity)))
        self._ring(p, cx, cy, r=88,  w=0.7, spd=-18, ph=t+1.1,  arc=130, col=QColor(255, 90, 25, int(70 * ity)))
        self._amp_bars(p, cx, cy, amp, t)
        self._core(p, cx, cy, scale=react, intensity=ity)

    def _processing(self, p, cx, cy, t):
        self._glow(p, cx, cy, 0.70)
        self._ring(p, cx, cy, r=66,  w=1.8, spd=65,  ph=t,       arc=270, col=QColor(255, 38, 0, 190))
        self._ring(p, cx, cy, r=80,  w=1.1, spd=-42, ph=t + 0.5, arc=210, col=QColor(255, 75, 18, 130))
        self._ring(p, cx, cy, r=95,  w=0.7, spd=28,  ph=t + 1.3, arc=150, col=QColor(195, 18, 0,  85))
        self._scan(p, cx, cy, (t * 185) % 360)
        pulse = 0.94 + 0.06 * math.sin(t * math.pi * 5)
        self._core(p, cx, cy, scale=pulse, intensity=0.88)

    def _speaking(self, p, cx, cy, t):
        self._glow(p, cx, cy, 0.80)
        for i in range(3):
            ph = (t * 0.65 + i * 0.38) % 1.0
            r  = 58 + ph * 85
            a  = int(210 * (1.0 - ph))
            self._ring(p, cx, cy, r=r, w=1.6, spd=0, ph=0, arc=360, col=QColor(255, 55, 0, a))
        pulse = 0.93 + 0.08 * math.sin(t * math.pi * 7)
        self._core(p, cx, cy, scale=pulse, intensity=1.0)

    # ── Primitivos de desenho ─────────────────────────────────────────────────

    def _glow(self, p: QPainter, cx, cy, intensity: float):
        """Camadas de brilho difuso ao redor do orbe."""
        for i in range(7, 0, -1):
            r = self.ORB_R + i * 11
            a = max(0, int(22 * intensity * (1.0 - i / 8.0)))
            p.setBrush(QBrush(QColor(255, 18, 0, a)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _core(self, p: QPainter, cx, cy, scale: float = 1.0, intensity: float = 1.0):
        """Orbe central com gradiente radial e highlight."""
        r = self.ORB_R * scale

        # Corpo principal
        g = QRadialGradient(cx, cy, r)
        g.setColorAt(0.00, QColor(255,  95,  45, int(230 * intensity)))
        g.setColorAt(0.45, QColor(255,  28,   0, int(170 * intensity)))
        g.setColorAt(1.00, QColor(140,   0,   0, 0))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Highlight interno (canto superior esquerdo)
        ox, oy = cx - r * 0.18, cy - r * 0.18
        r2 = r * 0.32
        g2 = QRadialGradient(ox, oy, r2)
        g2.setColorAt(0.0, QColor(255, 210, 170, int(175 * intensity)))
        g2.setColorAt(1.0, QColor(255,  80,  20, 0))
        p.setBrush(QBrush(g2))
        p.drawEllipse(QRectF(ox - r2, oy - r2, r2 * 2, r2 * 2))

    def _ring(self, p: QPainter, cx, cy, r, w, spd, ph, arc, col: QColor):
        """Arco giratório."""
        angle = (ph * spd) % 360
        pen = QPen(col)
        pen.setWidthF(w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(rect, int(angle * 16), int(arc * 16))

    def _amp_bars(self, p: QPainter, cx, cy, amp: float, t: float):
        """Barras radiais que reagem à amplitude do microfone."""
        n = 14
        inner = self.ORB_R + 8
        for i in range(n):
            theta = (i / n) * 2 * math.pi
            bar_h = 6 + amp * 22 * abs(math.sin(t * 9 + i * 0.75))
            x1 = cx + math.cos(theta) * inner
            y1 = cy + math.sin(theta) * inner
            x2 = cx + math.cos(theta) * (inner + bar_h)
            y2 = cy + math.sin(theta) * (inner + bar_h)
            pen = QPen(QColor(255, 85, 22, int(140 + 115 * amp)))
            pen.setWidthF(2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

    def _scan(self, p: QPainter, cx, cy, deg: float):
        """Linha de varredura giratória (estado processing)."""
        rad = math.radians(deg)
        r = self.ORB_R - 6
        pen = QPen(QColor(255, 155, 55, 200))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.drawLine(int(cx), int(cy),
                   int(cx + math.cos(rad) * r),
                   int(cy + math.sin(rad) * r))


# ─────────────────────────────────────────────────────────────────────────────
#  UltronWindow — janela principal frameless
# ─────────────────────────────────────────────────────────────────────────────

class UltronWindow(QWidget):
    WIN_W = 270
    WIN_H = 315

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint       |
            Qt.WindowType.WindowStaysOnTopHint      |
            Qt.WindowType.Tool                       # sem entrada na taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIN_W, self.WIN_H)

        # ── Layout ────────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 18, 0, 16)
        layout.setSpacing(4)

        self.orb = OrbWidget(self)
        layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)

        self.label = QLabel("inicializando...", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFixedWidth(self.WIN_W - 20)
        self.label.setStyleSheet("""
            QLabel {
                color: rgba(255, 90, 60, 175);
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9pt;
                letter-spacing: 2px;
                background: transparent;
            }
        """)
        layout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)

        # ── Fila polling ──────────────────────────────────────────────────────
        qt = QTimer(self)
        qt.timeout.connect(self._drain_queue)
        qt.start(40)   # 25 checks/s é suficiente

        # ── Arrastar ──────────────────────────────────────────────────────────
        self._drag: QPoint | None = None

        # Posiciona canto inferior direito da tela principal
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right()  - self.WIN_W - 20,
                  screen.bottom() - self.WIN_H - 20)

    # ── Fila ──────────────────────────────────────────────────────────────────

    def _drain_queue(self):
        while not ui_queue.empty():
            try:
                cmd, data = ui_queue.get_nowait()
            except queue.Empty:
                break
            if cmd == "state":
                self.orb.set_state(data)
            elif cmd == "text":
                # Trunca texto longo e coloca em maiúsculas (estética sci-fi)
                txt = str(data)[:48].upper()
                self.label.setText(txt)
            elif cmd == "amplitude":
                self.orb.set_amplitude(data)

    # ── Plano de fundo arredondado ─────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fundo escuro arredondado
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_BG_COL))
        p.drawRoundedRect(self.rect(), 18, 18)

        # Borda sutil vermelha
        pen = QPen(_BORDER)
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 17, 17)

    # ── Arrastar a janela ──────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def mouseDoubleClickEvent(self, _):
        self.close()   # duplo clique fecha
