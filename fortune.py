"""问心处 · 起卦引擎(开源独立版) fortune-stall

铁律「卦面即印章」: 卦面只能由服务端产出并立即落账; 随机起法(铜钱/骰子)
在服务端摇, 落地即锁。AI/人只负责断, 不负责起、更不许改。

依赖: 标准库 + cnlunar(农历/干支落款, 缺席时自动降级为公历落款)。
技能包: 需要 https://github.com/wave2234/divination-skills 置于 SKILLS_DIR。
"""
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", ROOT / "skills"))
DB_PATH = Path(os.environ.get("FORTUNE_DB", ROOT / "data" / "fortune.db"))
PERSONA = os.environ.get("PERSONA", "摊主")
_ZHI = "子丑寅卯辰巳午未申酉戌亥"


def _hour_zhi(h):
    return _ZHI[((int(h) + 1) // 2) % 12]


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def _ensure():
    with _connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS fortune_sessions ("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, question TEXT, "
                  "method TEXT, mode TEXT, args_json TEXT, face TEXT, "
                  "seal TEXT DEFAULT '', verdict TEXT DEFAULT '', author TEXT DEFAULT '')")


def _seal_line():
    """落款: 公历 + 农历 + 干支 + 节气(cnlunar 权威); 失败降级为纯公历。
    返回 (seal, 日干支) —— 后者用于六爻脚本内干支的交叉校验。"""
    now = datetime.now()
    try:
        import cnlunar
        a = cnlunar.Lunar(now, godType="8char")
        parts = [now.strftime("%Y-%m-%d"),
                 (a.lunarMonthCn or "") + (a.lunarDayCn or ""),
                 "%s年[%s] %s月 %s日" % (a.year8Char, a.chineseYearZodiac, a.month8Char, a.day8Char)]
        term = getattr(a, "todaySolarTerms", "") or ""
        if term and term != "无":
            parts.append(term)
        return " · ".join(p for p in parts if p), a.day8Char
    except Exception:
        return now.strftime("%Y-%m-%d %H:%M"), ""


def _script(method):
    d = {"xiaoliuren": SKILLS_DIR / "xiaoliuren" / "scripts" / "qigua.py",
         "liuyao": SKILLS_DIR / "liuyao" / "scripts" / "paigua.py",
         "tarot": SKILLS_DIR / "tarot" / "scripts" / "draw.py"}
    return d.get(method)


def _run(method, argv):
    sp = _script(method)
    if not sp or not sp.exists():
        raise RuntimeError("技能包缺席: 请把 divination-skills 克隆到 " + str(SKILLS_DIR)
                           + " (见 README「快速开始」)")
    r = subprocess.run([sys.executable, str(sp)] + [str(a) for a in argv],
                       capture_output=True, text=True, timeout=25, cwd=str(sp.parent.parent))
    if r.returncode != 0:
        raise RuntimeError("起卦脚本报错: " + ((r.stderr or r.stdout) or "")[:300])
    return (r.stdout or "").strip()


def cast(args):
    _ensure()
    question = str(args.get("question") or "").strip()
    if not question:
        raise ValueError("无事不占: 先给 question(所测何事)")
    method = str(args.get("method") or "").strip()
    mode = str(args.get("mode") or "time").strip()
    now = datetime.now()
    nowstr = now.strftime("%Y-%m-%d %H:%M")
    hz = str(args.get("hour") or _hour_zhi(now.hour)).strip()
    a, b, c = args.get("a"), args.get("b"), args.get("c")
    name, dong, yaos, gender = args.get("name"), args.get("dong"), args.get("yaos"), args.get("gender")
    if method == "xiaoliuren":
        if mode == "time":
            argv = ["date", nowstr]
        elif mode == "lunar":
            if a is None or b is None:
                raise ValueError("lunar 模式要 a=农历月 b=农历日, hour=时辰支")
            argv = ["lunar", int(a), int(b), hz]
        elif mode == "numbers":
            if a is None or b is None or c is None:
                raise ValueError("numbers 模式要 a b c 三个数(问者报的数, 不许自造随机)")
            argv = ["numbers", int(a), int(b), int(c), "--hour", hz]
        elif mode == "gua":
            if not name:
                raise ValueError("gua 模式要 name=三宫卦名(空格分隔)")
            argv = ["gua"] + str(name).split() + ["--hour", hz]
        else:
            raise ValueError("小六壬认 time/lunar/numbers/gua; 摇骰是随机起法, 走 /api/fortune/roll")
        if gender:
            argv += ["--gender", str(gender)]
    elif method == "liuyao":
        if mode == "time":
            argv = ["date", nowstr]
        elif mode == "numbers":
            if a is None or b is None or c is None:
                raise ValueError("numbers 要 a(下卦) b(上卦) c(动爻)三个数, 由问者报出")
            argv = ["numbers", int(a), int(b), int(c)]
        elif mode == "gua":
            if not name:
                raise ValueError("gua 模式要 name=卦名, 可配 dong=动爻(1-6)")
            argv = ["gua", str(name)] + (["--dong", int(dong)] if dong else [])
        elif mode == "yao":
            if not yaos:
                raise ValueError("yao 模式要 yaos=六个数(6/7/8/9, 自下而上, 空格分隔)")
            argv = ["yao"] + str(yaos).split()
        else:
            raise ValueError("六爻认 time/numbers/gua/yao; 摇铜钱走 /api/fortune/roll")
    elif method == "tarot":
        m = {"time": "three", "single": "one", "one": "one", "three": "three",
             "cross": "celtic", "celtic": "celtic", "custom": "custom", "interpret": "interpret"}.get(mode)
        if not m:
            raise ValueError("塔罗牌阵认 one单牌 / three三牌 / celtic凯尔特十字 / custom自定张数 / interpret自报牌名")
        if m == "custom":
            if a is None:
                raise ValueError("custom 要 a=张数")
            argv = ["custom", int(a), "-q", question]
        elif m == "interpret":
            ns = str(name or "").split()
            if not ns:
                raise ValueError("interpret 要 name=牌名(空格分隔, 逆位写 reversed:牌名)")
            argv = ["interpret"] + ns
        else:
            argv = [m, "-q", question]
    else:
        raise ValueError("method 只认 xiaoliuren / liuyao / tarot")
    face = _run(method, argv)
    seal, day_gz = _seal_line()
    warn = ""
    if day_gz and method == "liuyao" and (day_gz + "日") not in face and day_gz not in face:
        warn = "\n⚠ 脚本内算干支与日历权威(" + day_gz + "日)不符, 断卦以日历为准"
    with _connect() as c2:
        cur = c2.execute("INSERT INTO fortune_sessions (created_at,question,method,mode,args_json,face,seal,author)"
                         " VALUES (?,?,?,?,?,?,?,?)",
                         (now.strftime("%Y-%m-%d %H:%M:%S"), question[:200], method, mode,
                          json.dumps([str(x) for x in argv], ensure_ascii=False), face[:12000], seal, PERSONA))
        sid = cur.lastrowid
    return ("🎐 卦局 #" + str(sid) + " 已落印 · " + seal + "\n问: " + question + "\n" + "─" * 24 + "\n"
            + face + warn + "\n" + "─" * 24 + "\n卦面为服务端印章, 只断不改。")


def roll(kind, question, gender=""):
    """摊位随机起法: dice=三枚骰子走小六壬, coin=三枚铜钱摇六次走六爻。服务端摇, 落地即锁。"""
    import random
    if not str(question or "").strip():
        raise ValueError("先说所问何事")
    if kind == "dice":
        pips = [random.randint(1, 6) for _ in range(3)]
        out = cast({"question": question, "method": "xiaoliuren", "mode": "numbers",
                    "a": pips[0], "b": pips[1], "c": pips[2], "gender": gender})
        return {"kind": "dice", "pips": pips, "text": out}
    if kind == "coin":
        tosses, yaos = [], []
        for _ in range(6):
            backs = sum(1 for _ in range(3) if random.random() < 0.5)
            tosses.append(backs)
            yaos.append({3: 9, 2: 8, 1: 7, 0: 6}[backs])
        out = cast({"question": question, "method": "liuyao", "mode": "yao",
                    "yaos": " ".join(str(y) for y in yaos)})
        return {"kind": "coin", "tosses": tosses, "yaos": yaos, "text": out}
    raise ValueError("摊位摇法只有 dice(骰子) 和 coin(铜钱)")


def register(app, require_auth):
    """把问心处 API 挂到任意 FastAPI 应用上。require_auth 为 FastAPI 依赖(可为空实现)。"""
    from fastapi import Depends, HTTPException, Request
    _ensure()

    @app.post("/api/fortune/roll", dependencies=[Depends(require_auth)])
    async def _f_roll(req: Request):
        b = await req.json()
        try:
            return roll(str(b.get("kind") or ""), b.get("question") or "", b.get("gender") or "")
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.post("/api/fortune/cast", dependencies=[Depends(require_auth)])
    async def _f_cast(req: Request):
        b = await req.json()
        try:
            return {"text": cast(b)}
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.get("/api/fortune/recent", dependencies=[Depends(require_auth)])
    def _f_recent(n: int = 8):
        _ensure()
        with _connect() as c:
            rows = c.execute("SELECT id,created_at,question,method,mode,seal,verdict FROM fortune_sessions"
                             " ORDER BY id DESC LIMIT ?", (max(1, min(n, 30)),)).fetchall()
        return [{"id": r[0], "at": r[1], "q": r[2], "method": r[3], "mode": r[4],
                 "seal": r[5], "verdict": r[6]} for r in rows]

    @app.get("/api/fortune/session/{sid}", dependencies=[Depends(require_auth)])
    def _f_one(sid: int):
        _ensure()
        with _connect() as c:
            r = c.execute("SELECT id,created_at,question,method,mode,face,seal,verdict"
                          " FROM fortune_sessions WHERE id=?", (sid,)).fetchone()
        if not r:
            raise HTTPException(404, "no such session")
        return {"id": r[0], "at": r[1], "q": r[2], "method": r[3], "mode": r[4],
                "face": r[5], "seal": r[6], "verdict": r[7]}

    @app.post("/api/fortune/verdict", dependencies=[Depends(require_auth)])
    async def _f_verdict(req: Request):
        b = await req.json()
        _ensure()
        try:
            sid = int(b.get("id"))
        except Exception:
            raise HTTPException(400, "要 id(卦局号)")
        v = str(b.get("verdict") or "").strip()[:4000]
        with _connect() as c:
            cur = c.execute("UPDATE fortune_sessions SET verdict=? WHERE id=?", (v, sid))
            if cur.rowcount == 0:
                raise HTTPException(404, "no such session")
        return {"ok": True, "id": sid}
    # ── AI 解读（DeepSeek） ──
    @app.post("/api/fortune/interpret", dependencies=[Depends(require_auth)])
    async def _f_interpret(req: Request):
        import httpx
        b = await req.json()
        sid = b.get("id")
        face = b.get("face", "")
        question = b.get("question", "")
        method = b.get("method", "")
        
        if not face:
            raise HTTPException(400, "缺少卦象数据")
        
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(500, "未配置 AI API Key")
        
        prompt = f"""你是一位精通传统占卜的解读师。请根据以下卦象信息，给出专业的解读。

占卜方式：{method}
问事：{question}
卦象：
{face}

请从以下几个方面解读：
1. 卦象本身的含义
2. 当前形势分析
3. 建议与启示

语气温和、有智慧感，避免绝对化判断。"""
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "system", "content": "你是一位温和、智慧的占卜解读师，精通小六壬、六爻、塔罗等传统占卜体系。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 2000
                    }
                )
                data = resp.json()
                if "choices" not in data:
                    raise Exception(data.get("error", {}).get("message", "AI 返回异常"))
                result = data["choices"][0]["message"]["content"]
        except Exception as e:
            raise HTTPException(500, f"AI 调用失败：{str(e)}")
        
        return {"ok": True, "interpretation": result}
