from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo_artifacts"


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def write_page(name: str, body: str, title: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(
        f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <style>
    :root {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1d1d1f;
      background: #ece7dc;
    }}
    body {{ margin: 0; }}
    main {{ width: 1180px; min-height: 760px; margin: 0 auto; padding: 42px; box-sizing: border-box; }}
    h1 {{ margin: 0 0 8px; font-size: 36px; letter-spacing: 0; }}
    p {{ line-height: 1.65; }}
    .muted {{ color: #6d665c; }}
    .layout {{ display: grid; grid-template-columns: 360px 1fr; gap: 28px; align-items: start; margin-top: 26px; }}
    .phone {{
      width: 330px;
      min-height: 660px;
      border-radius: 36px;
      background: #111;
      padding: 14px;
      box-shadow: 0 26px 70px rgba(0,0,0,.22);
    }}
    .screen {{
      min-height: 632px;
      border-radius: 27px;
      overflow: hidden;
      background: #a9d58f;
      position: relative;
    }}
    .chat-head {{ background: #f7f7f7; padding: 18px 16px; font-weight: 750; border-bottom: 1px solid #ddd; }}
    .chat {{ padding: 18px 12px 70px; }}
    .bubble {{
      max-width: 245px;
      padding: 10px 12px;
      margin: 10px 0;
      border-radius: 16px;
      font-size: 14px;
      line-height: 1.45;
      box-shadow: 0 1px 1px rgba(0,0,0,.08);
      white-space: pre-wrap;
    }}
    .bot {{ background: #fff; border-top-left-radius: 5px; }}
    .user {{ background: #d8f8c6; margin-left: auto; border-top-right-radius: 5px; }}
    .input {{ position: absolute; left: 12px; right: 12px; bottom: 14px; background: #fff; border-radius: 22px; padding: 12px 16px; color: #8a8a8a; }}
    .card {{ background: #fff; border: 1px solid #d9d2c7; border-radius: 10px; padding: 18px; margin-bottom: 16px; }}
    .steps {{ display: grid; gap: 12px; }}
    .step {{ display: grid; grid-template-columns: 34px 1fr; gap: 12px; align-items: start; }}
    .num {{ width: 30px; height: 30px; border-radius: 50%; background: #1f6feb; color: #fff; display: grid; place-items: center; font-weight: 800; }}
    .db {{ background: #fbfbfa; border: 1px solid #d7d1c7; border-radius: 10px; overflow: hidden; box-shadow: 0 18px 50px rgba(0,0,0,.08); }}
    .db-head {{ padding: 20px 22px; border-bottom: 1px solid #dfd9cf; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; background: #fff; }}
    th, td {{ border-bottom: 1px solid #ece7df; padding: 13px 12px; text-align: left; vertical-align: top; }}
    th {{ color: #756f66; font-weight: 700; background: #fbfaf7; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 4px 9px; background: #e8f1ff; color: #1557b0; font-size: 12px; font-weight: 700; }}
    .ok {{ background: #e4f7df; color: #267a2a; }}
    .warn {{ background: #fff0ce; color: #8a5b00; }}
    code {{ background: #eee8dc; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
{body}
</body>
</html>
""",
        encoding="utf-8",
    )
    return path


def line_join_page() -> Path:
    body = """
<main>
  <h1>Demo 1: User 加入 LINE OA</h1>
  <p class="muted">使用者只要加入你的 LINE 官方帳號，之後所有資料都從 LINE 入口送進系統。</p>
  <div class="layout">
    <div class="phone">
      <div class="screen">
        <div class="chat-head">LINE Notion Capture</div>
        <div class="chat">
          <div class="bubble bot">歡迎加入！傳文字、網址、想法或待辦，我會整理後寫入 Notion。</div>
          <div class="bubble bot">目前支援：文字 / URL。圖片、語音、檔案可在下一階段接入。</div>
        </div>
        <div class="input">Message</div>
      </div>
    </div>
    <section>
      <div class="card">
        <h2>入口設計</h2>
        <div class="steps">
          <div class="step"><div class="num">1</div><div>朋友加入 LINE OA。</div></div>
          <div class="step"><div class="num">2</div><div>LINE webhook 會把訊息送到 Render 上的 <code>/line/webhook</code>。</div></div>
          <div class="step"><div class="num">3</div><div>系統驗證 LINE signature，避免假請求。</div></div>
        </div>
      </div>
      <div class="card">
        <h2>這一步的目的</h2>
        <p>把使用者入口壓到最低：不用裝新 app，不用填表單，只要傳 LINE 訊息。</p>
      </div>
    </section>
  </div>
</main>
"""
    return write_page("01-line-oa-join.html", body, "LINE OA Join Demo")


def line_message_page(capture: dict) -> Path:
    result = capture["result"]
    text = capture["input_text"]
    body = f"""
<main>
  <h1>Demo 2: User 傳資料給 LINE OA</h1>
  <p class="muted">這是 dry-run 模擬出的完整對話：收到資料、整理、寫入 Notion、回傳結果。</p>
  <div class="layout">
    <div class="phone">
      <div class="screen">
        <div class="chat-head">LINE Notion Capture</div>
        <div class="chat">
          <div class="bubble user">{esc(text)}</div>
          <div class="bubble bot">收到，正在整理到 Notion...</div>
          <div class="bubble bot">已整理完成\\n{esc(result["title"])}\\n分類:{esc(result["category"])}\\nAI:{esc(result["provider"])}\\n{esc(result["notion_url"])}</div>
        </div>
        <div class="input">Message</div>
      </div>
    </div>
    <section>
      <div class="card">
        <h2>系統實際處理結果</h2>
        <p><strong>Title:</strong> {esc(result["title"])}</p>
        <p><strong>Category:</strong> <span class="pill">{esc(result["category"])}</span></p>
        <p><strong>AI Provider:</strong> <span class="pill warn">{esc(result["provider"])}</span></p>
        <p><strong>Notion URL:</strong> <code>{esc(result["notion_url"])}</code></p>
      </div>
      <div class="card">
        <h2>後端保護</h2>
        <p>訊息會先寫入 SQLite，狀態從 <code>received</code> → <code>processing</code> → <code>completed</code>。同一個 LINE message id 重送時不會重複寫 Notion。</p>
      </div>
    </section>
  </div>
</main>
"""
    return write_page("02-line-send-data.html", body, "LINE Send Data Demo")


def notion_page(captures: list[dict]) -> Path:
    rows = []
    for item in captures:
        rows.append(
            f"""<tr>
  <td>{esc(item.get("title") or "(pending)")}</td>
  <td><span class="pill ok">{esc(item.get("status"))}</span></td>
  <td><span class="pill">{esc(item.get("category"))}</span></td>
  <td>{esc(item.get("source_user"))}</td>
  <td>{esc(item.get("source_type"))}</td>
  <td>{esc(item.get("provider"))}</td>
  <td>{esc(item.get("duplicate_count"))}</td>
</tr>"""
        )
    body = f"""
<main>
  <h1>Demo 3: Notion Database 呈現</h1>
  <p class="muted">正式環境會寫入 Notion database。此畫面用 dry-run 的 SQLite 紀錄重現 database 欄位，欄位結構與 Notion 寫入 payload 對齊。</p>
  <div class="db">
    <div class="db-head">
      <h2>LINE Capture Inbox</h2>
      <p class="muted">Properties: Name, Status, Category, Source User, Source Type, Summary, Tags, AI Provider, LINE Message ID, Created At</p>
    </div>
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Status</th>
          <th>Category</th>
          <th>Source User</th>
          <th>Source Type</th>
          <th>AI Provider</th>
          <th>Duplicate Count</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>
  <div class="card" style="margin-top: 18px;">
    <h2>Notion Page Body</h2>
    <p>每筆資料點開後，正文會包含三段：<code>摘要</code>、<code>原始訊息</code>、<code>來源資訊</code>。</p>
  </div>
</main>
"""
    return write_page("03-notion-database.html", body, "Notion Database Demo")


def main() -> None:
    capture_path = OUT / "capture_result.json"
    captures_path = OUT / "captures.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    captures = json.loads(captures_path.read_text(encoding="utf-8"))["captures"]
    pages = [line_join_page(), line_message_page(capture), notion_page(captures)]
    print("\\n".join(str(page) for page in pages))


if __name__ == "__main__":
    main()
