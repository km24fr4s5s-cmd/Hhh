#!/usr/bin/env python3
"""Genera dos vídeos animados (estilo meme) con bocadillo de texto y voz sintética.

Uso: python3 scripts/make_videos.py IMG_LAB IMG_FIESTA
Requiere: ffmpeg, espeak-ng, Pillow, numpy.
"""
import math, random, subprocess, sys, wave, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 720, 1280, 25
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
TEXTO = ("¡Nuestra victoria de hoy, según Hugo, es para que bajen el precio "
         "de las compresas y que se acaben los cólicos del dolor de regla!")
OUT = os.path.join(os.path.dirname(__file__), "..", "videos")


def tts(path, voice, speed, pitch):
    subprocess.run(["espeak-ng", "-v", voice, "-s", str(speed), "-p", str(pitch),
                    "-w", path, TEXTO], check=True)
    with wave.open(path) as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    hop = sr // FPS
    env = np.array([np.sqrt(np.mean(data[i:i + hop] ** 2)) if len(data[i:i + hop]) else 0
                    for i in range(0, len(data), hop)])
    env = env / (env.max() or 1)
    return env, len(data) / sr


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def wrap(draw, text, font, maxw):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines


def bubble(frame, words_shown, box, tail, fill, outline, txt_col):
    d = ImageDraw.Draw(frame)
    x0, y0, x1, y1 = box
    font = ImageFont.truetype(FONT_B, 34)
    d.polygon([tail[0], tail[1], tail[2]], fill=fill, outline=outline)
    d.rounded_rectangle(box, radius=36, fill=fill, outline=outline, width=5)
    d.polygon([tail[0], tail[1], tail[2]], fill=fill)
    lines = wrap(d, TEXTO, font, x1 - x0 - 50)
    count = 0
    y = y0 + 22
    for line in lines:
        x = x0 + 25
        for word in line.split():
            if count < words_shown:
                d.text((x, y), word, font=font, fill=txt_col)
            x += d.textlength(word + " ", font=font)
            count += 1
        y += 44


def title(frame, text, y, col, stroke):
    d = ImageDraw.Draw(frame)
    font = ImageFont.truetype(FONT_B, 52)
    tw = d.textlength(text, font=font)
    d.text(((W - tw) / 2, y), text, font=font, fill=col, stroke_width=6, stroke_fill=stroke)


def make(src, name, crop, focus, voice, speed, pitch, style):
    wav = f"/tmp/{name}.wav"
    env, dur = tts(wav, voice, speed, pitch)
    intro, outro = 0.8, 1.5
    total = int((intro + dur + outro) * FPS)
    base = Image.open(src).convert("RGB")
    if crop:
        base = base.crop(crop)
    base = cover(base, int(W * 1.25), int(H * 1.25))
    nwords = len(TEXTO.split())
    rnd = random.Random(7)
    confetti = [(rnd.uniform(0, W), rnd.uniform(-H, 0), rnd.uniform(3, 8), rnd.uniform(-2, 2),
                 rnd.choice(style["confetti"])) for _ in range(90)]

    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-itsoffset", str(intro), "-i", wav,
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-preset", "medium",
                          "-c:a", "aac", "-b:a", "128k", "-af", "apad", "-shortest",
                          "-movflags", "+faststart", os.path.join(OUT, f"{name}.mp4")],
                         stdin=subprocess.PIPE)
    for f in range(total):
        t = f / FPS
        ts = t - intro
        a = env[int(ts * FPS)] if 0 <= ts < dur and int(ts * FPS) < len(env) else 0.0
        # zoom lento + "rebote" al ritmo de la voz
        z = 1.0 + 0.12 * (t / (total / FPS)) + 0.04 * a
        ang = 2.5 * math.sin(t * 6) * a
        bw, bh = int(base.width / z), int(base.height / z)
        bw, bh = min(bw, base.width), min(bh, base.height)
        fx, fy = focus
        cx = int(min(max(fx * base.width, bw / 2), base.width - bw / 2))
        cy = int(min(max(fy * base.height - 30 * a, bh / 2), base.height - bh / 2))
        frame = base.crop((cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2)).resize((W, H))
        if ang:
            frame = frame.rotate(ang, resample=Image.BICUBIC, expand=False).resize((W, H))
            frame = cover(frame.crop((20, 20, W - 20, H - 20)), W, H)
        # viñeta inferior para legibilidad
        grad = Image.new("L", (1, H))
        for yy in range(H):
            grad.putpixel((0, yy), int(170 * max(0, (yy - H * 0.55) / (H * 0.45))))
        dark = Image.new("RGB", (W, H), (0, 0, 0))
        frame = Image.composite(dark, frame, grad.resize((W, H)))

        title(frame, style["title"], 40, style["title_col"], style["title_stroke"])
        if ts >= 0:
            shown = nwords if ts >= dur else int(nwords * ts / dur) + 1
            bubble(frame, shown, style["box"], style["tail"], style["fill"], style["outline"], style["txt"])
        if ts >= dur - 0.3:
            d = ImageDraw.Draw(frame)
            for (x, y0, sp, dx, col) in confetti:
                k = (t - intro - dur + 0.3) * FPS
                yy = y0 + sp * k * 2
                if 0 < yy < H:
                    xx = x + dx * k + 10 * math.sin(k / 5 + x)
                    d.rectangle((xx, yy, xx + 10, yy + 16), fill=col)
        p.stdin.write(frame.tobytes())
    p.stdin.close(); p.wait()
    os.remove(wav)


if __name__ == "__main__":
    lab, fiesta = sys.argv[1], sys.argv[2]
    os.makedirs(OUT, exist_ok=True)
    make(lab, "video1_laboratorio", None, (0.62, 0.40), "es", 150, 55, dict(
        title="¡VICTORIA! 🏆".replace(" 🏆", ""), title_col=(255, 215, 0), title_stroke=(120, 0, 90),
        box=(40, 860, 680, 1200), tail=[(360, 860), (430, 860), (470, 760)],
        fill=(255, 255, 255), outline=(200, 0, 120), txt=(40, 0, 60),
        confetti=[(255, 80, 160), (255, 215, 0), (0, 200, 255), (140, 255, 100)]))
    make(fiesta, "video2_fiesta", (0, 110, 1320, 2800), (0.65, 0.40), "es", 165, 40, dict(
        title="¡SEGÚN HUGO!", title_col=(80, 255, 140), title_stroke=(60, 0, 80),
        box=(40, 880, 680, 1220), tail=[(380, 880), (450, 880), (520, 780)],
        fill=(30, 10, 50), outline=(80, 255, 140), txt=(255, 255, 255),
        confetti=[(80, 255, 140), (255, 60, 200), (255, 230, 0), (100, 160, 255)]))
