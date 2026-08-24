"""问心处 · 起卦引擎(开源独立版) fortune-stall 铁律「卦面即印章」: 卦面只能由服务端产出并立即落账; 随机起法(铜钱/骰子) 在服务端摇, 落地即锁。AI/人只负责断, 不负责起、更不许改。 依赖: 标准库 + cnlunar(农历/干支落款, 缺席时自动降级为公历落款)。 技能包: 需要 https://github.com/wave2234/divination-skills 置于 SKILLS_DIR。 """
import json
import os
import sqlite3
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", ROOT / "skills"))
DB_PATH = Path(os.environ.get("FORTUNE_DB", ROOT / "data" / "fortune.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
PERSONA = os.environ.get("PERSONA", "摊主")
_ZHI = "子丑寅卯辰巳午未申酉戌亥"

def _hour_zhi(h):
    return _ZHI[((int(h) + 1) // 2) % 12]

def _connect():
    """优先使用 PostgreSQL；未设置 DATABASE_URL 时保留 SQLite 方便本地开发。"""
    if DATABASE_URL:
        import psycopg
        return psycopg.connect(DATABASE_URL)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def _ensure():
    with _connect() as c:
        if DATABASE_URL:
            c.execute("CREATE TABLE IF NOT EXISTS fortune_sessions ("
                      "id BIGSERIAL PRIMARY KEY, created_at TEXT NOT NULL, question TEXT NOT NULL, "
                      "method TEXT NOT NULL, mode TEXT NOT NULL, args_json TEXT NOT NULL, face TEXT NOT NULL, "
                      "seal TEXT DEFAULT '', verdict TEXT DEFAULT '', author TEXT DEFAULT '', "
                      "visitor_id TEXT NOT NULL DEFAULT '')")
            c.execute("CREATE INDEX IF NOT EXISTS fortune_sessions_visitor_id_idx "
                      "ON fortune_sessions (visitor_id, id DESC)")
        else:
            c.execute("CREATE TABLE IF NOT EXISTS fortune_sessions ("
                      "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, question TEXT, "
                      "method TEXT, mode TEXT, args_json TEXT, face TEXT, "
                      "seal TEXT DEFAULT '', verdict TEXT DEFAULT '', author TEXT DEFAULT '', "
                      "visitor_id TEXT NOT NULL DEFAULT '')")
        
        if not DATABASE_URL:
            columns = {row[1] for row in c.execute("PRAGMA table_info(fortune_sessions)").fetchall()}
            if "visitor_id" not in columns:
                c.execute("ALTER TABLE fortune_sessions ADD COLUMN visitor_id TEXT NOT NULL DEFAULT ''")
        
        # 创建邀请码表
        ...
        
        # 创建邀请码表
        if DATABASE_URL:
            c.execute("""
                CREATE TABLE IF NOT EXISTS invite_codes (
                    id BIGSERIAL PRIMARY KEY,
                    code VARCHAR(20) UNIQUE NOT NULL,
                    owner VARCHAR(100) NOT NULL,
                    total_limit INTEGER NOT NULL,
                    used_count INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    note TEXT
                )
            """)
            try:
                c.execute("ALTER TABLE fortune_sessions ADD COLUMN invite_code VARCHAR(20)")
            except Exception:
                pass
        else:
            c.execute("""
                CREATE TABLE IF NOT EXISTS invite_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code VARCHAR(20) UNIQUE NOT NULL,
                    owner VARCHAR(100) NOT NULL,
                    total_limit INTEGER NOT NULL,
                    used_count INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    note TEXT
                )
            """)
            try:
                c.execute("ALTER TABLE fortune_sessions ADD COLUMN invite_code VARCHAR(20)")
            except Exception:
                pass

def _seal_line():
    """落款: 公历 + 农历 + 干支 + 节气(cnlunar 权威); 失败降级为纯公历。 返回 (seal, 日干支) ------ 后者用于六爻脚本内干支的交叉校验。"""
    now = datetime.now()
    try:
        import cnlunar
        a = cnlunar.Lunar(now, godType="8char")
        parts = [now.strftime("%Y-%m-%d"), (a.lunarMonthCn or "") + (a.lunarDayCn or ""), "%s年[%s] %s月 %s日" % (a.year8Char, a.chineseYearZodiac, a.month8Char, a.day8Char)]
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
        raise RuntimeError("技能包缺席: 请把 divination-skills 克隆到 " + str(SKILLS_DIR) + " (见 README「快速开始」)")
    r = subprocess.run([sys.executable, str(sp)] + [str(a) for a in argv], capture_output=True, text=True, timeout=25, cwd=str(sp.parent.parent))
    if r.returncode != 0:
        raise RuntimeError("起卦脚本报错: " + ((r.stderr or r.stdout) or "")[:300])
    return (r.stdout or "").strip()

def cast(args, visitor_id=""):
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
        m = {"time": "three", "single": "one", "one": "one", "three": "three", "cross": "celtic", "celtic": "celtic", "custom": "custom", "interpret": "interpret"}.get(mode)
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
        
    values = (now.strftime("%Y-%m-%d %H:%M:%S"), question[:200], method, mode, json.dumps([str(x) for x in argv], ensure_ascii=False), face[:12000], seal, PERSONA, visitor_id)
    
    with _connect() as c2:
        if DATABASE_URL:
            sid = c2.execute("INSERT INTO fortune_sessions "
                             "(created_at,question,method,mode,args_json,face,seal,author,visitor_id) "
                             "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", values).fetchone()[0]
        else:
            cur = c2.execute("INSERT INTO fortune_sessions "
                             "(created_at,question,method,mode,args_json,face,seal,author,visitor_id) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", values)
            sid = cur.lastrowid
            
    return ("🎐 卦局 #" + str(sid) + " 已落印 · " + seal + "\n问: " + question + "\n" + "─" * 24 + "\n" + face + warn + "\n" + "─" * 24 + "\n卦面为服务端印章, 只断不改。")

def roll(kind, question, gender="", visitor_id=""):
    """摊位随机起法: dice=三枚骰子走小六壬, coin=三枚铜钱摇六次走六爻。服务端摇, 落地即锁。"""
    import random
    if not str(question or "").strip():
        raise ValueError("先说所问何事")
        
    if kind == "dice":
        pips = [random.randint(1, 6) for _ in range(3)]
        out = cast({"question": question, "method": "xiaoliuren", "mode": "numbers", "a": pips[0], "b": pips[1], "c": pips[2], "gender": gender}, visitor_id)
        return {"kind": "dice", "pips": pips, "text": out}
        
    if kind == "coin":
        tosses, yaos = [], []
        for _ in range(6):
            backs = sum(1 for _ in range(3) if random.random() < 0.5)
            tosses.append(backs)
            yaos.append({3: 9, 2: 8, 1: 7, 0: 6}[backs])
        out = cast({"question": question, "method": "liuyao", "mode": "yao", "yaos": " ".join(str(y) for y in yaos)}, visitor_id)
        return {"kind": "coin", "tosses": tosses, "yaos": yaos, "text": out}
        
    raise ValueError("摊位摇法只有 dice(骰子) 和 coin(铜钱)")

def register(app, require_auth):
    """把问心处 API 挂到任意 FastAPI 应用上。require_auth 为 FastAPI 依赖(可为空实现)。"""
    from fastapi import Depends, HTTPException, Request, Header
    
    _ensure()

    def require_visitor(x_fortune_visitor: str = Header(default="")) -> str:
        """浏览器本地生成的匿名 UUID；只用来隔离不同访客的卦账。"""
        visitor = x_fortune_visitor.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", visitor):
            raise HTTPException(400, "缺少或无效的访客标识，请刷新页面后重试")
        return visitor

    @app.post("/api/fortune/roll", dependencies=[Depends(require_auth)])
    async def _f_roll(req: Request, visitor: str = Depends(require_visitor)):
        b = await req.json()
        try:
            return roll(str(b.get("kind") or ""), b.get("question") or "", b.get("gender") or "", visitor)
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.post("/api/fortune/cast", dependencies=[Depends(require_auth)])
    async def _f_cast(req: Request, visitor: str = Depends(require_visitor)):
        b = await req.json()
        try:
            return {"text": cast(b, visitor)}
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.get("/api/fortune/recent", dependencies=[Depends(require_auth)])
    def _f_recent(n: int = 8, visitor: str = Depends(require_visitor)):
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                rows = c.execute("SELECT id,created_at,question,method,mode,seal,verdict FROM fortune_sessions "
                                 "WHERE visitor_id=%s ORDER BY id DESC LIMIT %s", (visitor, max(1, min(n, 30)))).fetchall()
            else:
                rows = c.execute("SELECT id,created_at,question,method,mode,seal,verdict FROM fortune_sessions "
                                 "WHERE visitor_id=? ORDER BY id DESC LIMIT ?", (visitor, max(1, min(n, 30)))).fetchall()
        return [{"id": r[0], "at": r[1], "q": r[2], "method": r[3], "mode": r[4], "seal": r[5], "verdict": r[6]} for r in rows]

    @app.get("/api/fortune/session/{sid}", dependencies=[Depends(require_auth)])
    def _f_one(sid: int, visitor: str = Depends(require_visitor)):
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                r = c.execute("SELECT id,created_at,question,method,mode,face,seal,verdict "
                              "FROM fortune_sessions WHERE id=%s AND visitor_id=%s", (sid, visitor)).fetchone()
            else:
                r = c.execute("SELECT id,created_at,question,method,mode,face,seal,verdict "
                              "FROM fortune_sessions WHERE id=? AND visitor_id=?", (sid, visitor)).fetchone()
            if not r:
                raise HTTPException(404, "no such session")
        return {"id": r[0], "at": r[1], "q": r[2], "method": r[3], "mode": r[4], "face": r[5], "seal": r[6], "verdict": r[7]}

    @app.post("/api/fortune/verdict", dependencies=[Depends(require_auth)])
    async def _f_verdict(req: Request, visitor: str = Depends(require_visitor)):
        b = await req.json()
        _ensure()
        try:
            sid = int(b.get("id"))
        except Exception:
            raise HTTPException(400, "要 id(卦局号)")
        v = str(b.get("verdict") or "").strip()[:4000]
        with _connect() as c:
            if DATABASE_URL:
                cur = c.execute("UPDATE fortune_sessions SET verdict=%s WHERE id=%s AND visitor_id=%s", (v, sid, visitor))
            else:
                cur = c.execute("UPDATE fortune_sessions SET verdict=? WHERE id=? AND visitor_id=?", (v, sid, visitor))
            if cur.rowcount == 0:
                raise HTTPException(404, "no such session")
        return {"ok": True, "id": sid}

    @app.post("/api/fortune/ai_verdict", dependencies=[Depends(require_auth)])
    async def _f_ai_verdict(req: Request, visitor: str = Depends(require_visitor)):
        """根据卦局调用 DeepSeek 断卦，可自动存档"""
        import httpx
        b = await req.json()
        try:
            sid = int(b.get("id"))
        except Exception:
            raise HTTPException(400, "要 id(卦局号)")
        auto_save = bool(b.get("auto_save", True))
        
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                r = c.execute("SELECT id, question, method, face, seal FROM fortune_sessions "
                              "WHERE id=%s AND visitor_id=%s", (sid, visitor)).fetchone()
            else:
                r = c.execute("SELECT id, question, method, face, seal FROM fortune_sessions "
                              "WHERE id=? AND visitor_id=?", (sid, visitor)).fetchone()
            if not r:
                raise HTTPException(404, "no such session")
                
        method = r[2] or ""
        face = r[3] or ""
        question = r[1] or ""
        
        # 读取对应技能包 SKILL.md
        skill_map = {
            "xiaoliuren": SKILLS_DIR / "xiaoliuren" / "SKILL.md",
            "liuyao": SKILLS_DIR / "liuyao" / "SKILL.md",
            "tarot": SKILLS_DIR / "tarot" / "SKILL.md",
        }
        skill_path = skill_map.get(method)
        skill_text = ""
        if skill_path and skill_path.exists():
            skill_text = skill_path.read_text(encoding="utf-8")[:12000]
            
        system_prompt = (
            "你是一位严谨的传统占卜师。请严格遵循用户提供的技能包工作流进行断卦。"
            "输出格式要求：\n"
            "【断】先给出明确结论（1-3句）\n"
            "【卦理】用白话解释为什么这么断（3-6句）\n"
            "【建议】给出可执行的建议（可选）\n"
            "不要编造卦面内容，只根据提供的卦面和技能包断。"
        )
        
        user_prompt = f"""请根据以下技能包和卦面进行断卦。 【技能包】 {skill_text} 【所问之事】 {question} 【卦面】 {face} """
        
        api_key = os.environ.get("AI_API_KEY", "")
        base_url = os.environ.get("AI_BASE_URL", "https://api.deepseek.com").rstrip("/")
        model = os.environ.get("AI_MODEL", "deepseek-chat")
        
        if not api_key:
            raise HTTPException(500, "服务器未配置 AI_API_KEY")
            
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1500,
                    },
                )
                if resp.status_code != 200:
                    raise HTTPException(502, f"AI 接口返回错误: {resp.status_code} {resp.text[:200]}")
                    
                data = resp.json()
                verdict = data["choices"][0]["message"]["content"].strip()
        except httpx.TimeoutException:
            raise HTTPException(504, "AI 调用超时，请稍后重试")
        except Exception as e:
            raise HTTPException(502, f"调用 AI 失败: {str(e)[:200]}")
            
        if auto_save and verdict:
            with _connect() as c:
                if DATABASE_URL:
                    c.execute("UPDATE fortune_sessions SET verdict=%s WHERE id=%s AND visitor_id=%s", (verdict[:4000], sid, visitor))
                else:
                    c.execute("UPDATE fortune_sessions SET verdict=? WHERE id=? AND visitor_id=?", (verdict[:4000], sid, visitor))
                    
        return {"ok": True, "id": sid, "verdict": verdict}

    # ── 邀请码系统 ──
    
    @app.post("/api/fortune/verify_invite")
    async def _f_verify_invite(req: Request):
        """验证邀请码"""
        b = await req.json()
        code = b.get("code", "").strip().upper()
        if not code:
            raise HTTPException(400, "请输入邀请码")
        
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                row = c.execute(
                    "SELECT id, total_limit, used_count, active FROM invite_codes WHERE code = %s",
                    (code,)
                ).fetchone()
            else:
                row = c.execute(
                    "SELECT id, total_limit, used_count, active FROM invite_codes WHERE code = ?",
                    (code,)
                ).fetchone()
            
            if not row:
                raise HTTPException(401, "邀请码不存在")
            
            invite_id, total_limit, used_count, active = row
            
            if not active:
                raise HTTPException(403, "邀请码已失效")
            
            if used_count >= total_limit:
                raise HTTPException(403, f"邀请码已用完（{used_count}/{total_limit}）")
            
            remaining = total_limit - used_count
            return {"valid": True, "remaining": remaining}
    
    @app.post("/api/fortune/use_invite")
    async def _f_use_invite(req: Request):
        """记录使用并扣减次数"""
        b = await req.json()
        code = b.get("code", "").strip().upper()
        session_id = b.get("session_id")
        
        if not code or not session_id:
            raise HTTPException(400, "参数错误")
        
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                row = c.execute(
                    "SELECT id, total_limit, used_count, active FROM invite_codes WHERE code = %s",
                    (code,)
                ).fetchone()
                
                if not row or not row[3] or row[2] >= row[1]:
                    raise HTTPException(403, "邀请码无效或已用完")
                
                c.execute("UPDATE invite_codes SET used_count = used_count + 1 WHERE code = %s", (code,))
                c.execute("UPDATE fortune_sessions SET invite_code = %s WHERE id = %s", (code, session_id))
            else:
                row = c.execute(
                    "SELECT id, total_limit, used_count, active FROM invite_codes WHERE code = ?",
                    (code,)
                ).fetchone()
                
                if not row or not row[3] or row[2] >= row[1]:
                    raise HTTPException(403, "邀请码无效或已用完")
                
                c.execute("UPDATE invite_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
                c.execute("UPDATE fortune_sessions SET invite_code = ? WHERE id = ?", (code, session_id))
            
            remaining = row[1] - row[2] - 1
            return {"success": True, "remaining": remaining}
    
    def require_admin(x_admin_token: str = Header(default="")):
        """管理员认证"""
        admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
        if not admin_token:
            raise HTTPException(500, "管理员未配置")
        if x_admin_token != admin_token:
            raise HTTPException(401, "管理员密码错误")
    
    @app.get("/api/fortune/admin/invites")
    async def _f_get_invites(_: None = Depends(require_admin)):
        """获取所有邀请码"""
        _ensure()
        with _connect() as c:
            rows = c.execute("""
                SELECT id, code, owner, total_limit, used_count, active, created_at, note
                FROM invite_codes
                ORDER BY created_at DESC
            """).fetchall()
            
            return {
                "invites": [
                    {
                        "id": r[0],
                        "code": r[1],
                        "owner": r[2],
                        "total_limit": r[3],
                        "used_count": r[4],
                        "active": bool(r[5]),
                        "created_at": str(r[6]) if r[6] else None,
                        "note": r[7]
                    }
                    for r in rows
                ]
            }
    
    @app.post("/api/fortune/admin/invites")
    async def _f_create_invite(req: Request, _: None = Depends(require_admin)):
        """创建邀请码（自动生成随机码）"""
        import random
        import string
        
        b = await req.json()
        owner = b.get("owner", "").strip()
        total_limit = int(b.get("total_limit", 10))
        note = b.get("note", "").strip()
        
        if not owner:
            raise HTTPException(400, "请输入所属人")
        
        # 生成6位随机邀请码
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                while c.execute("SELECT 1 FROM invite_codes WHERE code = %s", (code,)).fetchone():
                    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                c.execute("""
                    INSERT INTO invite_codes (code, owner, total_limit, note)
                    VALUES (%s, %s, %s, %s)
                """, (code, owner, total_limit, note))
            else:
                while c.execute("SELECT 1 FROM invite_codes WHERE code = ?", (code,)).fetchone():
                    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                c.execute("""
                    INSERT INTO invite_codes (code, owner, total_limit, note)
                    VALUES (?, ?, ?, ?)
                """, (code, owner, total_limit, note))
            
            return {"success": True, "code": code}
    
    @app.delete("/api/fortune/admin/invites/{invite_id}")
    async def _f_delete_invite(invite_id: int, _: None = Depends(require_admin)):
        """删除邀请码"""
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                c.execute("DELETE FROM invite_codes WHERE id = %s", (invite_id,))
            else:
                c.execute("DELETE FROM invite_codes WHERE id = ?", (invite_id,))
            return {"success": True}
    
    @app.patch("/api/fortune/admin/invites/{invite_id}")
    async def _f_toggle_invite(invite_id: int, req: Request, _: None = Depends(require_admin)):
        """启用/禁用邀请码"""
        b = await req.json()
        active = b.get("active", True)
        
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                c.execute("UPDATE invite_codes SET active = %s WHERE id = %s", (active, invite_id))
            else:
                c.execute("UPDATE invite_codes SET active = ? WHERE id = ?", (int(active), invite_id))
            return {"success": True}
    
    @app.get("/api/fortune/admin/stats")
    async def _f_get_stats(_: None = Depends(require_admin)):
        """获取使用统计"""
        _ensure()
        with _connect() as c:
            if DATABASE_URL:
                today = c.execute("""
                    SELECT COUNT(*) FROM fortune_sessions
                    WHERE created_at::date = CURRENT_DATE
                """).fetchone()[0]
                
                week = c.execute("""
                    SELECT COUNT(*) FROM fortune_sessions
                    WHERE created_at::timestamp >= CURRENT_DATE - INTERVAL '7 days'
                """).fetchone()[0]
                
                records = c.execute("""
                    SELECT s.id, s.created_at, s.question, s.method, s.invite_code, i.owner
                    FROM fortune_sessions s
                    LEFT JOIN invite_codes i ON s.invite_code = i.code
                    ORDER BY s.id DESC
                    LIMIT 100
                """).fetchall()
            else:
                today = c.execute("""
                    SELECT COUNT(*) FROM fortune_sessions
                    WHERE DATE(created_at) = DATE('now')
                """).fetchone()[0]
                
                week = c.execute("""
                    SELECT COUNT(*) FROM fortune_sessions
                    WHERE created_at >= DATE('now', '-7 days')
                """).fetchone()[0]
                
                records = c.execute("""
                    SELECT s.id, s.created_at, s.question, s.method, s.invite_code, i.owner
                    FROM fortune_sessions s
                    LEFT JOIN invite_codes i ON s.invite_code = i.code
                    ORDER BY s.id DESC
                    LIMIT 100
                """).fetchall()
            
            return {
                "today": today,
                "week": week,
                "records": [
                    {
                        "id": r[0],
                        "time": str(r[1]) if r[1] else None,
                        "question": r[2],
                        "method": r[3],
                        "invite_code": r[4],
                        "owner": r[5]
                    }
                    for r in records
                ]
            }
