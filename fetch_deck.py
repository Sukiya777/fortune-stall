"""问心处 · 牌面下载器 —— 拉取韦特塔罗 1909 公版扫描并压成轻量 WebP

来源: Wikimedia Commons (Pamela Colman Smith 原画, 已进入公有领域)。
产物: static/tarot/*.webp 共 78 张、总计约 2MB。原图缓存在 .cache_src/ 便于重压。
礼貌抓取: 单线程 + 1.2s 间隔; 命中限流(429/403)会提示等待并可随时重跑续传。
"""
import hashlib
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
SRC = ROOT / ".cache_src"
OUT = ROOT / "static" / "tarot"
HDRS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fortune-stall-deck/1.0 "
                      "(+https://github.com/wave2234/fortune-stall)",
        "Accept": "image/jpeg,image/*;q=0.8,*/*;q=0.5"}

MAJOR = {0: "Fool", 1: "Magician", 2: "High_Priestess", 3: "Empress", 4: "Emperor",
         5: "Hierophant", 6: "Lovers", 7: "Chariot", 8: "Strength", 9: "Hermit",
         10: "Wheel_of_Fortune", 11: "Justice", 12: "Hanged_Man", 13: "Death",
         14: "Temperance", 15: "Devil", 16: "Tower", 17: "Star", 18: "Moon",
         19: "Sun", 20: "Judgement", 21: "World"}
SUITS = {"cups": "Cups", "wands": "Wands", "swords": "Swords", "pentacles": "Pents"}


def targets():
    t = [("major%02d" % n, "RWS_Tarot_%02d_%s.jpg" % (n, w)) for n, w in MAJOR.items()]
    for local, wiki in SUITS.items():
        for n in range(1, 15):
            t.append(("%s%02d" % (local, n), "%s%02d.jpg" % (wiki, n)))
    return t


def wiki_url(name):
    # 直连文件仓库, 路径按 MediaWiki 规则由文件名 md5 推出
    h = hashlib.md5(name.encode()).hexdigest()
    return "https://upload.wikimedia.org/wikipedia/commons/%s/%s/%s" % (h[0], h[:2], name)


def fetch(url, dst):
    req = urllib.request.Request(url, headers=HDRS)
    data = urllib.request.urlopen(req, timeout=30).read()
    if len(data) < 20000 or data[:2] != b"\xff\xd8":
        raise RuntimeError("拿到的不是完整 JPEG (%dB)" % len(data))
    dst.write_bytes(data)


def convert(src, dst):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    im = im.resize((340, round(h * 340 / w)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6))
    for q in (75, 66, 58, 50):
        im.save(dst, "WEBP", quality=q, method=6)
        if dst.stat().st_size <= 28672:
            break


def main():
    SRC.mkdir(exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    todo = targets()
    fails = []
    for i, (stem, wiki) in enumerate(todo, 1):
        out = OUT / (stem + ".webp")
        if out.exists() and out.stat().st_size > 5000:
            continue
        src = SRC / (stem + ".jpg")
        if not (src.exists() and src.stat().st_size > 20000):
            try:
                fetch(wiki_url(wiki), src)
            except urllib.error.HTTPError as e:
                if e.code in (429, 403):
                    print("⏳ 被限流(%d), 歇 90 秒再试一次…" % e.code)
                    time.sleep(90)
                    try:
                        fetch(wiki_url(wiki), src)
                    except Exception as e2:
                        print("✗ %s: %s (稍后重跑本脚本会自动续传)" % (stem, e2))
                        fails.append(stem)
                        continue
                else:
                    print("✗ %s: %s" % (stem, e))
                    fails.append(stem)
                    continue
            except Exception as e:
                print("✗ %s: %s" % (stem, e))
                fails.append(stem)
                continue
            time.sleep(1.2)
        convert(src, out)
        print("[%2d/78] %s %dKB" % (i, stem, out.stat().st_size // 1024))
    n = len(list(OUT.glob("*.webp")))
    tot = sum(p.stat().st_size for p in OUT.glob("*.webp")) / 1048576
    print("\n完成: %d/78 张, 共 %.2fMB" % (n, tot))
    if fails:
        print("未拿到:", " ".join(fails), "—— 稍后重跑即可续传")
        sys.exit(1)


if __name__ == "__main__":
    main()
