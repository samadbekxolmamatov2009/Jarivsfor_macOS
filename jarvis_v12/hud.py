"""J.A.R.V.I.S HUD — an Iron-Man style animated ring in the top-right corner.
Runs as a separate process; Jarvis sends it lines on stdin:  "<mode>\t<caption>"
modes: sleep | listen | think | speak
Test it alone:  python hud.py --demo
"""
import math
import sys
import threading
import time

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
                    NSBezierPath, NSColor, NSFont, NSFontAttributeName, NSForegroundColorAttributeName,
                    NSMutableParagraphStyle, NSParagraphStyleAttributeName, NSScreen, NSStatusWindowLevel,
                    NSTextAlignmentCenter, NSView, NSWindow, NSWindowStyleMaskBorderless)
from Foundation import NSMakeRect, NSObject, NSString, NSTimer

W, H = 300, 330
STATE = {"mode": "sleep", "caption": "", "alpha": 0.0, "quit": False, "changed": time.time()}
PALETTE = {"listen": (0.25, 0.85, 1.0), "think": (0.55, 0.55, 1.0), "speak": (0.45, 0.95, 1.0),
           "sleep": (0.25, 0.85, 1.0)}
SPIN = {"listen": 40, "think": 220, "speak": 90, "sleep": 20}


def rgba(c, a):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(c[0], c[1], c[2], max(0.0, min(1.0, a)))


def circle(cx, cy, r):
    return NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))


def arc(cx, cy, r, a0, a1, width, color):
    p = NSBezierPath.bezierPath()
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_((cx, cy), r, a0, a1)
    p.setLineWidth_(width)
    color.set()
    p.stroke()


class HUDView(NSView):
    def isOpaque(self):
        return False

    def drawRect_(self, rect):
        a = STATE["alpha"]
        if a <= 0.01:
            return
        t = time.time()
        mode = STATE["mode"] if STATE["mode"] != "sleep" else "listen"
        col = PALETTE[mode]
        cx, cy = W / 2, 200

        # pulse of the core
        if mode == "listen":
            core = 30 + 4 * math.sin(t * 3)
        elif mode == "think":
            core = 26 + 3 * math.sin(t * 9)
        else:
            core = 30 + 9 * abs(math.sin(t * 9)) * (0.6 + 0.4 * math.sin(t * 2.3))

        # glow
        for i in range(6, 0, -1):
            rgba(col, a * 0.05 * i).set()
            circle(cx, cy, core + i * 6).fill()
        rgba((0.85, 0.97, 1.0), a * 0.95).set()
        circle(cx, cy, core * 0.55).fill()
        rgba(col, a * 0.9).set()
        ring = circle(cx, cy, core)
        ring.setLineWidth_(3)
        ring.stroke()

        # outer thin rings
        for r, alpha in ((96, 0.25), (104, 0.12)):
            p = circle(cx, cy, r)
            p.setLineWidth_(1)
            rgba(col, a * alpha).set()
            p.stroke()

        # rotating arcs
        rot = (t * SPIN[mode]) % 360
        for k in range(3):
            s = rot + k * 120
            arc(cx, cy, 80, s, s + 70, 4, rgba(col, a * 0.85))
        # counter-rotating ticks
        rot2 = -(t * SPIN[mode] * 0.6) % 360
        for k in range(12):
            s = rot2 + k * 30
            arc(cx, cy, 64, s, s + 12, 2, rgba(col, a * 0.5))
        # speaking: equalizer ring
        if mode == "speak":
            for k in range(48):
                ang = math.radians(k * 7.5)
                amp = 6 + 10 * abs(math.sin(t * 7 + k * 0.7)) * abs(math.sin(t * 3.1 + k))
                x0, y0 = cx + 88 * math.cos(ang), cy + 88 * math.sin(ang)
                x1, y1 = cx + (88 + amp) * math.cos(ang), cy + (88 + amp) * math.sin(ang)
                p = NSBezierPath.bezierPath()
                p.moveToPoint_((x0, y0))
                p.lineToPoint_((x1, y1))
                p.setLineWidth_(2)
                rgba(col, a * 0.7).set()
                p.stroke()

        # title
        para = NSMutableParagraphStyle.alloc().init()
        para.setAlignment_(NSTextAlignmentCenter)
        title = {NSFontAttributeName: NSFont.boldSystemFontOfSize_(11),
                 NSForegroundColorAttributeName: rgba(col, a * 0.9), NSParagraphStyleAttributeName: para}
        label = {"listen": "LISTENING", "think": "THINKING", "speak": "SPEAKING"}[mode]
        NSString.stringWithString_(f"J.A.R.V.I.S  ·  {label}").drawInRect_withAttributes_(
            NSMakeRect(0, 308, W, 18), title)

        # caption box
        cap = STATE["caption"]
        if cap:
            box = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(12, 8, W - 24, 68), 12, 12)
            NSColor.colorWithCalibratedWhite_alpha_(0.05, a * 0.72).set()
            box.fill()
            rgba(col, a * 0.5).set()
            box.setLineWidth_(1)
            box.stroke()
            attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(13),
                     NSForegroundColorAttributeName: NSColor.colorWithCalibratedWhite_alpha_(1.0, a),
                     NSParagraphStyleAttributeName: para}
            NSString.stringWithString_(cap[:140]).drawInRect_withAttributes_(NSMakeRect(22, 12, W - 44, 58), attrs)


class Ticker(NSObject):
    def initWithWindow_view_(self, window, view):
        self = objc.super(Ticker, self).init()
        self.window, self.view = window, view
        return self

    def watch_(self, timer):
        """Slow check (3x per second). Starts the 30 fps animation only when Jarvis is awake."""
        if STATE["quit"]:
            NSApplication.sharedApplication().terminate_(None)
            return
        if STATE["mode"] != "sleep" and getattr(self, "fast", None) is None:
            self.fast = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1 / 30, self, "tick:", None, True)

    def tick_(self, timer):
        if STATE["quit"]:
            NSApplication.sharedApplication().terminate_(None)
            return
        target = 0.0 if STATE["mode"] == "sleep" else 1.0
        STATE["alpha"] += (target - STATE["alpha"]) * 0.15
        if abs(STATE["alpha"] - target) < 0.005:
            STATE["alpha"] = target
        self.window.setAlphaValue_(STATE["alpha"])
        if STATE["alpha"] > 0:
            self.view.setNeedsDisplay_(True)
        elif STATE["mode"] == "sleep":            # faded out -> stop animating (saves battery)
            timer.invalidate()
            self.fast = None


def reader():
    for line in sys.stdin:
        mode, _, caption = line.rstrip("\n").partition("\t")
        if mode in PALETTE:
            STATE["mode"] = mode
            if caption or mode == "listen":
                STATE["caption"] = caption
            if mode == "sleep":
                STATE["caption"] = ""
    STATE["quit"] = True                       # Jarvis stopped -> HUD closes too


def demo():
    seq = [("listen", ""), ("think", "What's 17 times 23?"), ("speak", "That's 391."),
           ("listen", ""), ("sleep", "")]
    while True:
        for mode, cap in seq:
            STATE["mode"], STATE["caption"] = mode, cap
            time.sleep(3)


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)      # no Dock icon

    vf = NSScreen.mainScreen().visibleFrame()
    x = vf.origin.x + vf.size.width - W - 16
    y = vf.origin.y + vf.size.height - H - 8
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(x, y, W, H), NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setLevel_(NSStatusWindowLevel)
    win.setIgnoresMouseEvents_(True)                                        # clicks pass through
    win.setHasShadow_(False)
    win.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 8))              # all spaces, stationary, fullscreen
    view = HUDView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
    win.setContentView_(view)
    win.setAlphaValue_(0.0)
    win.orderFrontRegardless()

    ticker = Ticker.alloc().initWithWindow_view_(win, view)
    ticker.fast = None
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.33, ticker, "watch:", None, True)
    threading.Thread(target=demo if "--demo" in sys.argv else reader, daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()
