"""Build the allowlisted, backend-free GitHub Pages demo with the existing UI."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("chat.js", "chat-state.js", "demo.js", "travel.css", "destinations.png")


def build_demo(output: Path = ROOT / "docs") -> None:
    (output / "assets").mkdir(parents=True, exist_ok=True)
    html = (ROOT / "web/page/chat.html").read_text(encoding="utf-8")
    html = html.replace('<body>', '<body data-demo="true">')
    html = html.replace('href="/assets/', 'href="assets/').replace('src="/assets/', 'src="assets/')
    html = html.replace('href="/chat.html"', 'href="./"')
    html = html.replace('<title>行知 · 旅游知识库助手</title>', '<title>行知 · 旅游 RAG 项目演示</title>\n  <meta name="description" content="面向旅游场景的 RAG 项目作品，展示多路检索、来源追溯和旅行问答交互。公开站使用预设示例，无需登录。">')
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / ".nojekyll").touch()
    for name in ASSETS:
        shutil.copy2(ROOT / "web/assets" / name, output / "assets" / name)
    print(f"Static demo ready: {output}")


if __name__ == "__main__":
    build_demo()
