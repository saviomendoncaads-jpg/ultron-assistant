#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultron HUD — Red Nebula Redesign
Stack : PyQt6 puro (QPainter) — 60fps
Paleta: vermelho/crimson sobre fundo estelar negro
"""

import sys, math, time, random, queue
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore    import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui     import (
    QColor, QPainter, QPen, QBrush,
    QRadialGradient, QLinearGradient, QFont, QPainterPath,
)

try:
    from modules.ui import ui_queue
except ImportError:
    ui_queue = queue.Queue()

# ── Paleta: vermelho/crimson ──────────────────────────────────────────────────
_BG         = QColor(  3,   2,   6)
_RED        = QColor(220,  35,  15)
_RED_HOT    = QColor(255, 100,  50)
_RED_DIM    = QColor( 80,  12,   8)
_RED_MED    = QColor(170,  30,  15)
_CORE_WHITE = QColor(255, 240, 225)

# Anéis: raios e alpha (todos circulares, levíssima perspectiva)
_RINGS = [
    (52,  70, 0.7),
    (80,  55, 0.65),
    (108, 42, 0.60),
    (137, 33, 0.55),
    (168, 24, 0.50),
    (200, 16, 0.45),
]

# Compression vertical mínima — dá leve profundidade sem distorcer
_VERT = 0.93


def _pen(color: QColor, w: float = 1.0) -> QPen:
    p = QPen(color, w)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p

def _font(size: int, bold: bool = False, spacing: float = 2.5) -> QFont:
    f = QFont("Consolas", size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


# ─────────────────────────────────────────────────────────────────────────────
#  Partícula orbital — distribuídas ao longo dos anéis (como na imagem)
# ─────────────────────────────────────────────────────────────────────────────
class _Particle:
    __slots__ = ("radius", "angle", "speed", "size", "base_a", "phase", "ring_idx")

    def __init__(self, rng: random.Random):
        # Cada partícula nasce próxima a um anel
        ring_idx = rng.randint(0, len(_RINGS) - 1)
        ring_r   = _RINGS[ring_idx][0]
        spread   = rng.gauss(0, 14)
        self.radius   = max(18, min(220, ring_r + spread))
        self.angle    = rng.uniform(0, math.tau)
        # Velocidade kepleriana (mais rápido por dentro) + aleatoriedade
        base_spd      = 0.08 * (65 / max(self.radius, 30))
        self.speed    = base_spd * rng.uniform(0.5, 1.5) * (1 if rng.random() > 0.25 else -1)
        self.size     = rng.choices([0.6, 0.8, 1.0, 1.3, 1.8, 2.5, 3.5],
                                    weights=[20, 18, 16, 12, 8, 4, 2])[0]
        self.base_a   = rng.randint(55, 210)
        self.phase    = rng.uniform(0, math.tau)
        self.ring_idx = ring_idx


# ─────────────────────────────────────────────────────────────────────────────
#  Estrela de fundo
# ─────────────────────────────────────────────────────────────────────────────
class _Star:
    __slots__ = ("x", "y", "r", "base_a", "spd", "phase")

    def __init__(self, rng: random.Random, W: int, H: int):
        self.x      = rng.uniform(0, W)
        self.y      = rng.uniform(0, H)
        self.r      = rng.choices([0.4, 0.6, 0.9, 1.4], weights=[40, 30, 20, 10])[0]
        self.base_a = rng.randint(40, 180)
        self.spd    = rng.uniform(0.3, 2.0)
        self.phase  = rng.uniform(0, math.tau)


# ─────────────────────────────────────────────────────────────────────────────
#  HUDWindow
# ─────────────────────────────────────────────────────────────────────────────
class HUDWindow(QWidget):
    W = 500
    H = 580

    N_PARTICLES = 1100
    N_STARS     = 320

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)

        self._state     = "idle"
        self._amplitude = 0.0
        self._text      = ""
        self._t         = 0.0
        self._drag: QPoint | None = None
        self._last      = time.perf_counter()

        # Centro levemente acima do meio geométrico
        self._cx = self.W / 2
        self._cy = self.H / 2 - 10

        rng = random.Random(42)
        self._particles = [_Particle(rng) for _ in range(self.N_PARTICLES)]
        self._stars     = [_Star(rng, self.W, self.H) for _ in range(self.N_STARS)]

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(16)

        self._q_timer = QTimer(self)
        self._q_timer.timeout.connect(self._drain)
        self._q_timer.start(40)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    # ── Loop de animação ──────────────────────────────────────────────────────

    def _tick(self):
        now  = time.perf_counter()
        dt   = min(now - self._last, 0.05)
        self._last = now
        self._t   += dt
        for pt in self._particles:
            pt.angle += pt.speed * dt
        self.update()

    def _drain(self):
        while True:
            try:
                cmd, data = ui_queue.get_nowait()
            except Exception:
                break
            if   cmd == "state":
                self._state = str(data)
            elif cmd == "text":
                self._text = str(data)[:50].upper()
            elif cmd == "amplitude":
                target = max(0.0, min(1.0, float(data)))
                self._amplitude = self._amplitude * 0.55 + target * 0.45

    # ── paintEvent ────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p   = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t   = self._t
        amp = self._amplitude
        cx, cy = self._cx, self._cy

        self._draw_bg(p, cx, cy, amp)
        self._draw_stars(p, t)
        self._draw_orb(p, cx, cy, t, amp)
        self._draw_top_text(p, cx, cy, t)
        self._draw_bottom_text(p, t, amp)
        self._draw_left_panel(p, t, amp)
        self._draw_close_btn(p)
        p.end()

    # ── Camadas ───────────────────────────────────────────────────────────────

    def _draw_bg(self, p: QPainter, cx: float, cy: float, amp: float):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_BG))
        p.drawRoundedRect(self.rect(), 16, 16)

        # Glow vermelho difuso vindo do centro (como na imagem)
        glow_r = 260 + amp * 40
        g = QRadialGradient(QPointF(cx, cy), glow_r)
        g.setColorAt(0.00, QColor(100, 12,  6,  60))
        g.setColorAt(0.35, QColor( 60,  6,  3,  30))
        g.setColorAt(1.00, QColor(  0,  0,  0,   0))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(self.rect(), 16, 16)

        # Borda vermelha sutil
        p.setPen(_pen(QColor(180, 25, 12, 40), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1), 15, 15)

    def _draw_stars(self, p: QPainter, t: float):
        p.setPen(Qt.PenStyle.NoPen)
        for s in self._stars:
            flicker = 0.5 + 0.5 * math.sin(t * s.spd + s.phase)
            a = int(s.base_a * flicker)
            p.setBrush(QBrush(QColor(230, 220, 210, a)))
            p.drawEllipse(QRectF(s.x - s.r, s.y - s.r, s.r*2, s.r*2))

    def _draw_rings(self, p: QPainter, cx: float, cy: float, t: float, amp: float):
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, (radius, alpha, w) in enumerate(_RINGS):
            # Leve pulsação diferente por anel
            pulse = 1.0 + amp * 0.035 * math.sin(t * 2.5 + i * 0.8)
            r  = radius * pulse
            ry = r * _VERT

            col = QColor(200, 40, 20, int(alpha * 255))
            p.setPen(_pen(col, w))
            p.drawEllipse(QRectF(cx - r, cy - ry, r*2, ry*2))

            # Marcações brilhantes no anel (pequenos nós)
            n_nodes = 8 if i < 3 else 6
            for k in range(n_nodes):
                ang = math.tau * k / n_nodes + t * (0.04 + i * 0.01)
                nx  = cx + math.cos(ang) * r
                ny  = cy + math.sin(ang) * r * _VERT
                node_a = int((alpha + 0.15) * 255)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 80, 40, node_a)))
                nr = w * 1.4
                p.drawEllipse(QRectF(nx - nr, ny - nr, nr*2, nr*2))

    def _draw_particles(self, p: QPainter, cx: float, cy: float, t: float, amp: float):
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            # Raio com leve pulsação pela amplitude
            perturb = amp * 18 * math.sin(t * 1.8 + pt.phase)
            r = max(12, min(225, pt.radius + perturb))

            x = cx + math.cos(pt.angle) * r
            y = cy + math.sin(pt.angle) * r * _VERT

            # Proximidade ao centro → mais brilhante e quente
            prox = max(0.0, 1.0 - r / 220)
            a = int(pt.base_a * (0.4 + amp * 0.6) * (0.6 + prox * 0.6))
            a = max(6, min(235, a))

            # Cor: branco-quente no interior → vermelho → vermelho escuro nas bordas
            if prox > 0.65:
                col = QColor(255, int(160 * prox + 60), int(80 * prox), a)
            elif prox > 0.3:
                col = QColor(230, int(50 + 40 * prox), 20, a)
            else:
                col = QColor(180, 25, 12, a)

            sz = pt.size * (0.8 + amp * 0.5)
            p.setBrush(QBrush(col))
            p.drawEllipse(QRectF(x - sz/2, y - sz/2, sz, sz))

    def _draw_orb(self, p: QPainter, cx: float, cy: float, t: float, amp: float):
        p.setPen(Qt.PenStyle.NoPen)

        # ── Raios de estrela (4 diagonais que giram lentamente) ──────────────
        n_rays = 8
        ray_len_base = 55 + amp * 35
        for i in range(n_rays):
            ang = math.tau * i / n_rays + t * 0.12
            # Raios alternados: longos e curtos
            ray_len = ray_len_base if i % 2 == 0 else ray_len_base * 0.55
            ray_a   = int(60 + amp * 50) if i % 2 == 0 else int(35 + amp * 30)
            # Gradiente linear ao longo do raio
            x1, y1 = cx + math.cos(ang) * 6,       cy + math.sin(ang) * 6
            x2, y2 = cx + math.cos(ang) * ray_len, cy + math.sin(ang) * ray_len
            grad = QLinearGradient(QPointF(cx, cy), QPointF(x2, y2))
            grad.setColorAt(0.0, QColor(255, 200, 160, ray_a))
            grad.setColorAt(1.0, QColor(180,  20,   8,   0))
            ray_w = 2.5 if i % 2 == 0 else 1.2
            pen = QPen(QBrush(grad), ray_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        p.setPen(Qt.PenStyle.NoPen)

        # ── Glow externo difuso (halo vermelho) ───────────────────────────────
        glow_layers = [
            (110, QColor( 90,   8,   4,  12)),
            ( 80, QColor(130,  15,   6,  22)),
            ( 55, QColor(180,  25,  10,  38)),
            ( 35, QColor(220,  40,  15,  60)),
            ( 20, QColor(245,  70,  30,  90)),
        ]
        for gr, gc in glow_layers:
            gr_a = gr + amp * 18
            a    = min(255, gc.alpha() + int(amp * 30))
            p.setBrush(QBrush(QColor(gc.red(), gc.green(), gc.blue(), a)))
            p.drawEllipse(QRectF(cx - gr_a, cy - gr_a, gr_a*2, gr_a*2))

        # ── Corpo da estrela — gradiente branco → laranja → vermelho ─────────
        r_orb = 14 + amp * 4 + 1.5 * math.sin(t * 2.8)
        g = QRadialGradient(QPointF(cx, cy), r_orb)
        g.setColorAt(0.00, QColor(255, 255, 250, 255))
        g.setColorAt(0.20, QColor(255, 240, 180, 255))
        g.setColorAt(0.50, QColor(255, 100,  45, 220))
        g.setColorAt(0.80, QColor(180,  22,   8, 120))
        g.setColorAt(1.00, QColor( 60,   4,   2,   0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QRectF(cx - r_orb, cy - r_orb, r_orb*2, r_orb*2))

        # ── Núcleo — ponto branco puro ────────────────────────────────────────
        r_core = r_orb * 0.38
        g2 = QRadialGradient(QPointF(cx, cy), r_core)
        g2.setColorAt(0.0, QColor(255, 255, 255, 255))
        g2.setColorAt(1.0, QColor(255, 250, 230,   0))
        p.setBrush(QBrush(g2))
        p.drawEllipse(QRectF(cx - r_core, cy - r_core, r_core*2, r_core*2))

    def _draw_top_text(self, p: QPainter, cx: float, cy: float, t: float):
        # Linhas decorativas laterais
        ly = cy - 195
        p.setPen(_pen(QColor(200, 35, 15, 50), 0.6))
        p.drawLine(QPointF(cx - 90, ly), QPointF(cx - 48, ly))
        p.drawLine(QPointF(cx + 48, ly), QPointF(cx + 90, ly))

        # ULTRON
        p.setFont(_font(14, True, 5.5))
        p.setPen(_pen(QColor(255, 110, 60, 230)))
        p.drawText(QRectF(cx - 110, ly - 10, 220, 26),
                   Qt.AlignmentFlag.AlignCenter, "ULTRON")

        # STATUS: ACTIVE pulsante
        pulse_a = int(100 + 80 * abs(math.sin(t * 0.9)))
        p.setFont(_font(7, False, 3.5))
        p.setPen(_pen(QColor(200, 55, 25, pulse_a)))
        p.drawText(QRectF(cx - 110, ly + 18, 220, 16),
                   Qt.AlignmentFlag.AlignCenter, "STATUS:  ACTIVE")

    def _draw_bottom_text(self, p: QPainter, t: float, amp: float):
        labels = {
            "idle":       "AGUARDANDO",
            "listening":  "OUVINDO",
            "processing": "PROCESSANDO",
            "speaking":   "TRANSMITINDO",
        }
        label = labels.get(self._state, self._state.upper())

        alpha = 220
        if self._state == "listening":
            alpha = int(140 + 115 * abs(math.sin(t * 2.4)))

        # Linha decorativa
        p.setPen(_pen(QColor(200, 30, 12, 40), 0.6))
        p.drawLine(QPointF(55, self.H - 58), QPointF(self.W - 55, self.H - 58))

        p.setFont(_font(10, True, 6.0))
        p.setPen(_pen(QColor(220, 50, 20, alpha)))
        p.drawText(QRectF(0, self.H - 54, self.W, 22),
                   Qt.AlignmentFlag.AlignCenter, label)

        # Transcript
        if self._text and self._text not in ("AGUARDANDO", "OUVINDO", "PROCESSANDO"):
            p.setFont(_font(6, False, 1.5))
            p.setPen(_pen(QColor(180, 45, 20, 120)))
            p.drawText(QRectF(20, self.H - 30, self.W - 40, 16),
                       Qt.AlignmentFlag.AlignCenter, self._text[:52])

        # Barra de amplitude
        if amp > 0.02:
            bar_w = int((self.W - 80) * amp)
            cx_bar = self.W / 2
            grad = QLinearGradient(QPointF(40, 0), QPointF(self.W - 40, 0))
            grad.setColorAt(0.0, QColor(200, 30, 12,   0))
            grad.setColorAt(0.5, QColor(255, 70, 30, 150))
            grad.setColorAt(1.0, QColor(200, 30, 12,   0))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(cx_bar - bar_w/2, self.H - 12, bar_w, 2))

    def _draw_left_panel(self, p: QPainter, t: float, amp: float):
        px, py = 12, self.H - 155
        pw, ph = 44, 115

        p.setPen(_pen(QColor(200, 30, 12, 45), 0.7))
        p.setBrush(QBrush(QColor(180, 20, 8, 8)))
        p.drawRoundedRect(QRectF(px, py, pw, ph), 5, 5)

        p.setFont(_font(5, True, 2.0))
        p.setPen(_pen(QColor(200, 40, 15, 110)))
        p.drawText(QRectF(px, py + 4, pw, 12), Qt.AlignmentFlag.AlignCenter, "MIC")

        p.setPen(_pen(QColor(200, 30, 12, 35), 0.5))
        p.drawLine(QPointF(px+6, py+17), QPointF(px+pw-6, py+17))

        n = 12
        seg_h, seg_gap = 5, 2
        y0     = py + ph - 22
        filled = max(0, int(n * amp))

        for i in range(n):
            seg_y = y0 - i * (seg_h + seg_gap)
            lit   = i < filled
            if   i < 4:  col = QColor(190, 30, 12, 210 if lit else 22)
            elif i < 8:  col = QColor(220, 55, 20, 210 if lit else 22)
            else:         col = QColor(255, 90, 40, 210 if lit else 22)
            p.setBrush(QBrush(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(px+7, seg_y, pw-14, seg_h), 1.5, 1.5)

        p.setFont(_font(7, True, 0.5))
        p.setPen(_pen(QColor(200, 40, 15, 160)))
        p.drawText(QRectF(px, y0+7, pw, 14), Qt.AlignmentFlag.AlignCenter,
                   f"{amp:.2f}")

    def _draw_close_btn(self, p: QPainter):
        bx, by, br = self.W - 20, 20, 9
        p.setPen(_pen(QColor(200, 35, 15, 65), 0.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(bx-br, by-br, br*2, br*2))
        p.setPen(_pen(QColor(220, 50, 20, 90), 1.0))
        d = 4.5
        p.drawLine(QPointF(bx-d, by-d), QPointF(bx+d, by+d))
        p.drawLine(QPointF(bx+d, by-d), QPointF(bx-d, by+d))

    # ── Eventos de mouse ──────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            bx, by, br = self.W - 20, 20, 13
            pos = e.position()
            if (pos.x()-bx)**2 + (pos.y()-by)**2 < br**2:
                self.close()
                return
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, _):
        self._drag = None

    def mouseDoubleClickEvent(self, _):
        self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    # ── API de compatibilidade ────────────────────────────────────────────────

    def set_state(self, s: str):       self._state     = s
    def set_text(self, t: str):        self._text      = t[:50].upper()
    def set_amplitude(self, a: float): self._amplitude = max(0.0, min(1.0, a))


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point standalone (demo)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading

    app = QApplication(sys.argv)
    win = HUDWindow()
    win.show()

    def _demo():
        sequence = [
            ("idle",       "AGUARDANDO",   2.5),
            ("listening",  "OUVINDO",      3.5),
            ("processing", "PROCESSANDO",  2.0),
            ("speaking",   "TRANSMITINDO", 3.0),
        ]
        while True:
            for state, text, dur in sequence:
                ui_queue.put(("state", state))
                ui_queue.put(("text",  text))
                steps = int(dur / 0.05)
                for i in range(steps):
                    amp = abs(math.sin(i * 0.35)) * 0.85 if state == "listening" else 0.0
                    ui_queue.put(("amplitude", amp))
                    time.sleep(0.05)
                ui_queue.put(("amplitude", 0.0))

    threading.Thread(target=_demo, daemon=True).start()
    sys.exit(app.exec())
