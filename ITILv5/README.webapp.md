# ITIL 5 Foundation 刷题 web app (Phase 1 skeleton)

> 跟目录里的 `README.md`(备考资料索引)是两件事 — 那个是资料目录说明,
> 这个是刷题 app 的运行说明。

## 🎯 现状(Phase 1)

骨架完成,可以跑。**只有 1 道示例题**,Phase 2 才会解析官方样题 PDF。

**已有功能**:
- ✅ Flask 后端(端口 5002,与 CISSP exam 5001 隔离)
- ✅ SQLite 题库(`exam.sqlite`)
- ✅ 单页 SPA:题目展示 / 4 选项 / 提交 / 反馈 / 下一题
- ✅ 会话统计(已答 / 正确 / 准确率)
- ✅ 题目不重复(同一会话内)

**未做**(Phase 2+):
- ⏳ 解析 `ITIL_FND_官方考试样题_中文版/SP1/SP2` PDF 入库
- ⏳ 错题本 / 标记掌握
- ⏳ 选项乱序(防死记答案位置)
- ⏳ 按主题 / 难度筛选
- ⏳ 计时模拟考试模式
- ⏳ 进度面板 / 学习曲线

## 🚀 运行

依赖复用 `../.venv/`(已装好 Flask)。直接:

```bash
cd ITILv5
make up           # 启动
# 浏览器打开 http://127.0.0.1:5002
```

或者手动:

```bash
../.venv/bin/python app.py
```

## 📂 文件清单

```
ITILv5/
├── app.py              # Flask backend (~150 行)
├── templates/
│   └── index.html      # 单页 SPA (vanilla JS, ~150 行)
├── questions.json      # 题库 (Phase 1: 1 道示例)
├── exam.sqlite         # SQLite (首次启动自动创建)
├── Makefile            # up / down / restart / status / logs
└── README.webapp.md    # 本文件
```

## 🔌 API

| 端点 | 方法 | 用途 |
|---|---|---|
| `/` | GET | SPA 入口 |
| `/api/health` | GET | 状态 + 题数 |
| `/api/question` | GET | 随机一题(同会话内不重复) |
| `/api/answer` | POST | 提交答案 → 返回对错 + 解析 |
| `/api/stats` | GET | 当前会话统计 |

## 🧱 题库 schema (`questions.json`)

```json
{
  "id": "demo-001",
  "topic": "服务管理关键概念",
  "stem": "题干...",
  "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
  "correct": "A",
  "rationale": "解析..."
}
```

字段约定:
- `id` 唯一(Phase 2 解析 PDF 时按 SP1/SP2 + 题号生成,例如 `sp1-q01`)
- `correct` 必须大写字母 A-D
- `rationale` 可以留空字符串

## 🛠 我自己做什么 / 你复核什么

| 项 | 状态 |
|---|---|
| Flask 路由 / SQLite schema | ✅ 我做,你只需 `make up` 验证 |
| SPA UI / 选项交互 | ✅ 我做,你看 UX 是否顺 |
| Phase 2 PDF 解析 | ⏳ 等你给信号再开始 |
| launchd plist (开机自启) | ⏳ 等 web app 稳定再加 |
| 题库内容准确性 | ⚠️ 示例题我自己写的,需要你核对(ITIL 5 真实考纲) |