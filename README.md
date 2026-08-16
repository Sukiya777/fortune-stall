# 问心处 · fortune-stall

夜市尽头的一张算卦小摊 —— 自托管的占卜小站。
**小六壬 / 六爻 / 塔罗**三味齐备：骰子铜钱在服务端摇、韦特原画逐张翻、每一卦落印进账本。

> 🧭 **内功心法在姊妹仓库 [divination-skills](https://github.com/wave2234/divination-skills)**
> —— 小六壬、六爻、塔罗三套技能包（`SKILL.md` 工作流 + 资料分册 + 起卦脚本）。
> 本摊直接调用它起卦排盘；把里面的 `SKILL.md` 喂给你的 AI，它就知道怎么断这张卦面。

## 摊上有什么

- **深空星幕**：缓漂星尘 + 偶发流星的移动端优先界面，切后台自动省电
- **三法起卦**
  - 小六壬（快卦）：按时 / 农历 / 报数 / 掷骰子
  - 六爻（深卦）：按时 / 报数 / 摇铜钱 / 指定卦名·爻象
  - 塔罗（心镜）：单牌 / 三牌 / 凯尔特十字 / 自定张数 / 自报牌名解读
- **三种手上仪式**
  - 骰子：摇动落定，**落地即锁**；重摇须走仪式并写明缘由，随卦记档
  - 铜钱：真·外圆内方的方孔钱，浅铜为背、深铜为字（字面铸「元亨利貞」），六爻自下而上逐爻显现
  - 塔罗：按位次逐张翻牌，凯尔特十字有节奏地开；**逆位整张倒转**；牌背与星幕同源
- **真牌面**：Pamela Colman Smith 1909 年韦特原画，78 张压制后共约 2MB，本地自托管
- **卦账**：每一卦（问事 / 卦面 / 农历干支落款 / 断语）落进本地 SQLite，随时翻查
- **复制卦面**：一键把整张卦面递给任何 AI 或人来断，断语可存回账上

## 铁律「卦面即印章」

一切随机只在服务端发生 —— 骰子、铜钱、抽牌都由服务端摇定并**当场写入账本**。
前端只呈现结果、只放动画；AI 只负责断卦，不负责起卦，更不能改卦。
确定性起法（报数、指定卦名）的参数也必须由问者报出，杜绝"模型自造随机数"。

## 快速开始

```bash
git clone https://github.com/wave2234/fortune-stall
cd fortune-stall

# 1) 请入心法(起卦脚本与资料)
git clone https://github.com/wave2234/divination-skills skills

# 2) 装依赖
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 3) 下载并压制 78 张公版牌面(约 2MB; 限流会提示, 重跑自动续传)
.venv/bin/python fetch_deck.py

# 4) 开摊
.venv/bin/python server.py        # → http://127.0.0.1:3900
```

## 配置

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `HOST` / `PORT` | `127.0.0.1` / `3900` | 监听地址与端口 |
| `PERSONA` | `摊主` | 卦账落款的摊主名 |
| `FORTUNE_DB` | `./data/fortune.db` | 卦账 SQLite 位置 |
| `DATABASE_URL` | 空 | Supabase PostgreSQL 连接串；设置后卦账会持久化到云端，并优先于 `FORTUNE_DB` |
| `SKILLS_DIR` | `./skills` | divination-skills 所在目录 |
| `FORTUNE_TOKEN` | 空 | 设了则所有 API 要求 `Bearer` 令牌；前端在浏览器控制台执行 `localStorage.setItem('fortune_token','…')` 配对 |

> ⚠️ 默认只监听本机。放公网请自行加认证层（反向代理 Basic Auth / Cloudflare Access 等），或至少设 `FORTUNE_TOKEN`。

### 免费版持久化卦账（Supabase）

Render 免费实例的本地文件会在休眠、重启与重新部署后清空。要保留卦账：

1. 在 Supabase 新建一个免费项目。
2. 点项目顶部 **Connect**，复制 **Session pooler** 的连接串（端口 `5432`）。Render 是 IPv4 网络，应使用 pooler，不要使用 Direct connection。
3. 在 Render 的 Environment 新增 `DATABASE_URL`，把连接串粘贴为值（不要提交到 GitHub）。
4. 保存并手动重新部署。程序会自动创建 `fortune_sessions` 表。

每个浏览器会自动获得一个匿名访客标识；卦账只显示该浏览器创建的记录。清除浏览器网站数据或更换浏览器后，旧记录仍在数据库，但该浏览器不再能直接查看。

## 把卦交给 AI 断

1. 起卦后点 **「复制卦面 · 拿去给 AI 断」**
2. 连同 [divination-skills](https://github.com/wave2234/divination-skills) 里对应门类的 `SKILL.md` 一起贴给你的 AI
3. 断语写回卦账详情页的存档框，一事一档

卦面自带卦局编号与农历干支落款，AI 断卦时可直接引用；印章由服务端盖，谁也改不了。

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/fortune/cast` | 确定性起法（`question, method, mode, a/b/c, hour, name, dong, yaos, gender`）|
| POST | `/api/fortune/roll` | 随机起法（`kind: dice/coin, question`），服务端摇定 |
| GET | `/api/fortune/recent?n=8` | 卦账列表 |
| GET | `/api/fortune/session/{id}` | 单卦全档 |
| POST | `/api/fortune/verdict` | 断语记档（`id, verdict`）|

## 牌面来源与版权

- 塔罗牌面为 **Pamela Colman Smith** 绘制的 Rider–Waite–Smith 塔罗（1909），原画已进入公有领域
- `fetch_deck.py` 从 Wikimedia Commons 拉取扫描件并在本地压制为 WebP；**仓库本身不含任何图片**
- 农历、干支与节气落款由 [cnlunar](https://github.com/OPN48/cnlunar) 计算

## 免责

占卜是文化实践与自省工具，不构成医疗、法律、投资或任何专业建议。请勿据此做重大决策。

---

## English

**fortune-stall** is a self-hosted divination stall — a mobile-first web app under a drifting starfield, offering three traditions: **Xiao Liu Ren** (quick palm divination), **Liu Yao** (I-Ching hexagrams via nạp giáp), and **Tarot** with genuine RWS 1909 card art by Pamela Colman Smith (public domain, fetched & compressed locally by `fetch_deck.py`, ~2MB for all 78).

**The iron rule — "the cast is a seal":** all randomness happens server-side. Dice, coins and card draws are rolled by the server and written to the ledger the moment they land. The frontend only renders; an AI may *read* a cast, never *make* or *alter* one.

Rituals are tactile: dice lock on landing (re-rolls require a written reason, kept on record); three bronze coins — square-holed, light side = *bèi*, dark side bears「元亨利貞」— reveal six lines bottom-up; tarot cards flip one by one in spread order, reversals rotated 180°.

Every cast lands in a local SQLite ledger with a lunar-calendar seal (via cnlunar). One tap copies the full face to hand to any AI for a reading — pair it with the skill packs in the sister repo **[divination-skills](https://github.com/wave2234/divination-skills)** and write the verdict back into the ledger.

Quickstart mirrors the Chinese section above: clone, clone `divination-skills` into `skills/`, `pip install -r requirements.txt`, run `fetch_deck.py`, then `server.py` → `http://127.0.0.1:3900`. Localhost-only by default; add your own auth layer (or set `FORTUNE_TOKEN`) before exposing it.

Divination is a cultural practice and a mirror for self-reflection — not medical, legal, or financial advice.

## 许可 · License

MIT
