"""给 frontend/*.html 里的 /static/css、/static/js 引用加上版本号，避免浏览器缓存旧文件。"""
import pathlib
import re

VERSION = "20261108"
ROOT = pathlib.Path(r"E:\MedAgent\frontend")

pattern = re.compile(r'(?<=["\'])(/static/(?:css|js)/[^"\']+)(?=["\'])')


def add_version(html: str) -> str:
    def repl(m: re.Match) -> str:
        url = m.group(1)
        if "?v=" in url:
            return url
        return f"{url}?v={VERSION}"

    return pattern.sub(repl, html)


changed = []
for p in sorted(ROOT.glob("*.html")):
    src = p.read_text(encoding="utf-8")
    out = add_version(src)
    if out != src:
        p.write_text(out, encoding="utf-8")
        changed.append(p.name)

print("updated:", changed)
