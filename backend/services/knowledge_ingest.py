"""知识条目摄取：网页/公开链接、常见办公文档 → 正文文本（Markdown 近似）。"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_INGEST_BYTES = 12 * 1024 * 1024
_MAX_DOWNLOAD_BYTES = MAX_INGEST_BYTES
# PDF 正文拼接上限（避免极大文件撑爆内存）
_MAX_PDF_EXTRACT_CHARS = 2 * 1024 * 1024
# 静态 HTML 抽字极少时，尝试从内嵌 SPA 状态（如 __NEXT_DATA__）补全
_MIN_BODY_BEFORE_SPA_FALLBACK = 500
_MAX_SPA_STRINGS = 450
_MAX_SPA_EXTRACT_CHARS = 800_000


class _HtmlToTextParser(HTMLParser):
    """剥离标签，粗略保留可读文本（够用联调与普通网页）；复杂版式建议使用专用解析链。"""

    _SKIP = frozenset({"script", "style", "noscript", "template", "svg", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._depth_skip = 0

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self._SKIP:
            self._depth_skip += 1
            return
        if self._depth_skip:
            return
        if tag in (
            "br",
            "p",
            "div",
            "tr",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "article",
            "main",
            "section",
            "table",
            "thead",
            "tbody",
            "tfoot",
            "colgroup",
            "blockquote",
            "figure",
            "figcaption",
            "header",
            "footer",
            "aside",
            "hr",
            "dl",
            "dt",
            "dd",
        ):
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self._SKIP and self._depth_skip:
            self._depth_skip -= 1
            return

    def handle_data(self, data: str):
        if self._depth_skip:
            return
        chunk = html.unescape(data).strip()
        if chunk:
            self._parts.append(chunk + " ")

    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _walk_json_long_strings(obj: object, acc: list[str], *, min_len: int, max_strings: int) -> None:
    if len(acc) >= max_strings:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= min_len and any(c.isalpha() for c in s):
            acc.append(s)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in (
                "styles",
                "scriptLoader",
                "buildId",
                "assetPrefix",
                "runtimeConfig",
                "page",
                "query",
                "dynamicIds",
            ):
                continue
            _walk_json_long_strings(v, acc, min_len=min_len, max_strings=max_strings)
        return
    if isinstance(obj, list):
        for it in obj[:120]:
            _walk_json_long_strings(it, acc, min_len=min_len, max_strings=max_strings)


def _extract_text_from_spa_embedded_json(html_txt: str) -> str:
    """从 Next.js / 常见内嵌 JSON 脚本中捞取长文本，弥补纯标签解析只能得到空壳的问题。"""
    out: list[str] = []
    seen: set[str] = set()

    next_m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html_txt,
        re.I | re.DOTALL,
    )
    if next_m:
        raw = next_m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            buf: list[str] = []
            _walk_json_long_strings(data, buf, min_len=40, max_strings=_MAX_SPA_STRINGS)
            for s in buf:
                st = s.strip()
                if st.startswith(("http://", "https://", "//", "data:")):
                    continue
                if st in seen:
                    continue
                # 过滤明显是配置/路径串
                if st.count("/") > 12 and " " not in st:
                    continue
                seen.add(st)
                out.append(st)

    merged = "\n\n".join(out).strip()
    if len(merged) > _MAX_SPA_EXTRACT_CHARS:
        merged = merged[:_MAX_SPA_EXTRACT_CHARS] + "\n…（内嵌 JSON 提取过长已截断）"
    return merged


def _merge_html_visible_with_spa_fallback(html_txt: str, visible_plain: str) -> str:
    base = (visible_plain or "").strip()
    if len(base) >= _MIN_BODY_BEFORE_SPA_FALLBACK:
        return base
    extra = _extract_text_from_spa_embedded_json(html_txt)
    if not extra:
        return base
    note = "（以下为从页面内嵌数据尽力恢复的正文；复杂动态页仍可能不完整，可导出文件或手动粘贴）"
    if base:
        return f"{base}\n\n---\n{note}\n\n{extra}"
    return f"{note}\n\n{extra}"


def _should_try_notion_record_map(hostname: str) -> bool:
    """只对实际文档页域名尝试解析 recordMap（排除 notion.com 营销站等）。"""
    h = (hostname or "").strip().lower()
    if not h:
        return False
    return h.endswith("notion.so") or ".notion.so" in h or h.endswith("notion.site") or ".notion.site" in h


_UUID_LIKE = re.compile(r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$", re.I)


def _meaningful_leaf_string(s: str) -> bool:
    st = (s or "").strip()
    if len(st) < 1:
        return False
    if _UUID_LIKE.match(st):
        return False
    if len(st) == 1 and st.isascii() and st.isalpha():
        return False
    tiny_style = frozenset(
        {"b", "i", "s", "_", "a", "default", "blue", "gray", "brown", "orange", "yellow", "green", "red", "pink", "purple"}
    )
    if st.lower() in tiny_style:
        return False
    return True


def _flatten_notion_property_ast(node: object, acc: list[str]) -> None:
    """递归展开 Notion properties 常见的嵌套 [['文本段'], ['同块续行'] ...]。"""
    if isinstance(node, str):
        if _meaningful_leaf_string(node):
            acc.append(node)
        return
    if isinstance(node, list):
        if not node:
            return
        first = node[0]
        if isinstance(first, str):
            tail_nodes = node[1:]
            if _meaningful_leaf_string(first):
                acc.append(first)
            for tail in tail_nodes:
                if isinstance(tail, str):
                    if _meaningful_leaf_string(tail):
                        acc.append(tail)
                elif isinstance(tail, list):
                    _flatten_notion_property_ast(tail, acc)
            return
        for it in node:
            _flatten_notion_property_ast(it, acc)


def _property_value_to_plain(props_val: object) -> str:
    acc: list[str] = []
    _flatten_notion_property_ast(props_val, acc)
    return "".join(acc).strip()


def _gather_child_ids(raw_content: object) -> list[str]:
    if not isinstance(raw_content, list):
        return []
    out: list[str] = []
    for item in raw_content:
        if isinstance(item, str) and item:
            out.append(item)
        elif isinstance(item, list) and item and isinstance(item[0], str):
            out.append(item[0])
    return out


def _block_record_map_from_obj(obj: object) -> dict | None:
    """兼容 {recordMap:{block:{...}}} 与顶层 {block:{...}}。"""
    if not isinstance(obj, dict):
        return None
    if isinstance(obj.get("recordMap"), dict):
        inner = obj["recordMap"].get("block")
        return inner if isinstance(inner, dict) else None
    inner = obj.get("block")
    return inner if isinstance(inner, dict) else None


def _find_record_map_in_next_data(html_txt: str) -> dict | None:
    """优先从 __NEXT_DATA__ 正确解析 JSON，查找 recordMap，比原始字符串扫描更可靠。"""
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html_txt,
        re.I | re.DOTALL,
    )
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError):
        return None

    def _find(obj: object):
        if isinstance(obj, dict):
            if "recordMap" in obj:
                rm = obj["recordMap"]
                if isinstance(rm, dict) and isinstance(rm.get("block"), dict):
                    return {"block": rm["block"]}
            for v in obj.values():
                res = _find(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for it in obj:
                res = _find(it)
                if res:
                    return res
        return None

    return _find(data)


def _yield_record_maps_in_html(html_txt: str):
    # 优先用 __NEXT_DATA__ 解析（更稳）
    rm = _find_record_map_in_next_data(html_txt)
    if rm:
        yield rm

    decoder = json.JSONDecoder()
    scan = html_txt[: min(len(html_txt), 8_000_000)]
    for needle in ('"recordMap"', "'recordMap'"):
        pos = 0
        while True:
            i = scan.find(needle, pos)
            if i < 0:
                break
            brace = scan.find("{", i)
            if brace < 0:
                break
            try:
                obj, idx_end = decoder.raw_decode(scan, brace)
            except json.JSONDecodeError:
                pos = i + len(needle)
                continue
            blocks = _block_record_map_from_obj(obj)
            if blocks:
                yield {"block": blocks}
            pos = max(i + len(needle), idx_end)


def _resolve_record_block_id(blocks: dict, cid: str) -> str | None:
    if not cid:
        return None
    if cid in blocks:
        return cid
    if cid.startswith(("block:", "collection:")):
        tail = cid.split(":", 1)[-1]
        if tail in blocks:
            return tail
        if cid in blocks:
            return cid
    prefixed = f"block:{cid}"
    if prefixed in blocks:
        return prefixed
    return None


def _collect_block_roots(blocks: dict) -> list[str]:
    mentioned: set[str] = set()
    for blk in blocks.values():
        if not isinstance(blk, dict):
            continue
        val = blk.get("value")
        if not isinstance(val, dict):
            continue
        mentioned.update(_gather_child_ids(val.get("content")))
    roots = [bid for bid in blocks.keys() if bid not in mentioned]
    if not roots:
        roots = list(blocks.keys())
    return roots


def _outline_notion_via_record_map(record: dict[str, dict]) -> list[str]:
    """按块 content 树深度优先拼接文本；无法解析父子关系时再退回零散块抽取。"""
    blocks = record.get("block")
    if not isinstance(blocks, dict) or not blocks:
        return []

    seen_walk: set[str] = set()
    ordered_lines: list[str] = []

    def dfs(bid: str) -> None:
        if bid in seen_walk:
            return
        seen_walk.add(bid)
        blk = blocks.get(bid)
        if not isinstance(blk, dict):
            return
        val = blk.get("value")
        if not isinstance(val, dict):
            return

        props = val.get("properties")
        lines_here: list[str] = []
        if isinstance(props, dict):
            for _pname, pval in props.items():
                pl = _property_value_to_plain(pval)
                if pl:
                    lines_here.append(pl)
        blob = "\n".join(lines_here).strip()
        if blob:
            ordered_lines.append(blob)

        for cid in _gather_child_ids(val.get("content")):
            nid = _resolve_record_block_id(blocks, cid)
            if nid:
                dfs(nid)

    roots = _collect_block_roots(blocks)
    visited_roots = 0
    for rid in roots:
        if visited_roots > 1200:
            break
        dfs(rid)
        visited_roots += 1

    if len(ordered_lines) < max(12, len(blocks) // 80):
        # 树不完整时补拾零：避免漏块
        for bid, blk in blocks.items():
            if bid in seen_walk:
                continue
            val = (blk or {}).get("value")
            if not isinstance(val, dict):
                continue
            props = val.get("properties")
            if not isinstance(props, dict):
                continue
            row: list[str] = []
            for _pk, pv in props.items():
                pl = _property_value_to_plain(pv)
                if pl:
                    row.append(pl)
            t = "\n".join(row).strip()
            if t and t not in ordered_lines:
                ordered_lines.append(t)

    uniq: list[str] = []
    seen_line: set[str] = set()
    for ln in ordered_lines:
        k = ln.strip()
        if not k or k in seen_line:
            continue
        seen_line.add(k)
        uniq.append(k)
    return uniq


def _extract_notion_record_map_plain(html_txt: str) -> str:
    all_lines: list[str] = []
    for rm_frag in _yield_record_maps_in_html(html_txt):
        all_lines.extend(_outline_notion_via_record_map(rm_frag))
        if len(all_lines) > 9000:
            break
    out = "\n\n".join(all_lines).strip()
    lim = min(_MAX_SPA_EXTRACT_CHARS, 1_600_000)
    if len(out) > lim:
        out = out[:lim] + "\n…（Notion recordMap 提取过长已截断）"
    return out


def _apply_notion_body_enrichment(hostname: str, html_txt: str, merged_body: str) -> str:
    if not _should_try_notion_record_map(hostname):
        return merged_body
    nt = _extract_notion_record_map_plain(html_txt).strip()
    base = merged_body.strip()
    if not nt:
        hint = (
            "\n\n—\n未能从页面内嵌的 Notion「recordMap」解析出正文。"
            "该链接可能需登录、仅客户端渲染或未公开。"
            "请使用 Notion 的「导出为 Markdown/HTML」上传，或改用 **notion.site** 公开页的「Share to web」可读链接。"
        )
        return base + hint if base else hint.strip()

    nt_len, base_len = len(nt), len(base)
    banner = (
        "（以下内容来自解析 Notion 页面内嵌的 recordMap（块正文）；若在 Notion 中编辑过复杂组件，请以导出文件为准。）\n\n"
    )
    # 重要：SSR + __NEXT_DATA__ 常产生比 recordMap 更长的噪声串，不能与 nt 比「总长」判断是否采用。
    if nt_len >= 400 or nt_len >= base_len:
        return f"{banner}{nt}".strip()
    if nt_len >= 140:
        return f"{base}\n\n---\n{banner}{nt}".strip()
    # 过少字符可能是误匹配的 recordMap；保留 baseline
    if base:
        return f"{base}\n\n{banner}\n{nt}".strip()
    return f"{banner}{nt}".strip()


def _charset_candidates_from_headers_and_html_sniff(ct_header: str, prefix: bytes) -> list[str]:
    """Collect Content-Type charset + common <meta charset=…> guesses; order-preserving."""

    cand: list[str] = []

    def _add(name: str) -> None:
        n = re.sub(r'^["\']|["\']$', "", name.strip())
        if not n:
            return
        aliases = {
            "utf8": "utf-8",
            "ascii": "utf-8",
            "cp936": "gb18030",
            "gb2312": "gb18030",
            "chinese_gbk": "gb18030",
        }
        key = aliases.get(n.lower(), n.lower())
        if key not in cand:
            cand.append(key)

    cm = re.search(r"charset=([^;\s]+)", ct_header or "", re.I)
    if cm:
        _add(cm.group(1))

    head_lc = prefix.decode("latin-1", errors="ignore").lower()
    m = re.search(r"<meta[^>]*charset\s*=\s*[\"']?\s*([^\"'\s/>]+)", head_lc)
    if m:
        _add(html.unescape(m.group(1)))
    hm = re.search(
        r"http-equiv\s*=\s*[\"']?\s*content-type[\"']?[^>]+content\s*=\s*[\"']([^\"']+)[\"']",
        head_lc,
        re.I,
    )
    if hm:
        sub = html.unescape(hm.group(1))
        sm = re.search(r"charset=([^;\s]+)", sub, re.I)
        if sm:
            _add(sm.group(1))

    _add("utf-8")
    _add("gb18030")
    return cand


def _decode_http_body_bytes(raw_bytes: bytes, ctype_header: str, sniff_html_meta: bool) -> str:
    prefix = raw_bytes[: min(len(raw_bytes), 65536)] if sniff_html_meta else b""
    cand = _charset_candidates_from_headers_and_html_sniff(ctype_header, prefix)

    seen: list[str] = []
    for c in cand:
        if c not in seen:
            seen.append(c)
    if "utf-8" not in seen:
        seen.append("utf-8")

    for enc in seen:
        try:
            return raw_bytes.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _assert_safe_http_url(raw: str) -> str:
    u = urlparse(raw.strip())
    if u.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError("仅支持 http(s) 链接")
    if not u.hostname:
        raise ValueError("无效的 URL")
    host = u.hostname.lower()
    if host in {"localhost"} or host.endswith(".local"):
        raise ValueError("出于安全策略，暂不允许抓取 localhost / .local 地址（请改用内网网关或导出后上传文件）")
    return raw.strip()


def fetch_url_body(url: str) -> tuple[str, str]:
    """
    GET 远端 URL，返回 (建议标题, 正文)。
    对 HTML 做简单正文抽取；纯文本响应则直接使用。
    """
    safe_url = _assert_safe_http_url(url)
    headers = {"User-Agent": "DataLensKnowledgeBot/1.0 (+internal-sync)"}
    with httpx.Client(timeout=35.0, follow_redirects=True, headers=headers) as client:
        with client.stream("GET", safe_url) as resp:
            resp.raise_for_status()
            ctype_header = resp.headers.get("content-type") or ""
            chunks: list[bytes] = []
            total = 0
            for block in resp.iter_bytes(chunk_size=65536):
                total += len(block)
                if total > _MAX_DOWNLOAD_BYTES:
                    raise ValueError("页面体积超过上限，请先导出为文件后上传")
                chunks.append(block)
            raw_bytes = b"".join(chunks)

    ctype = ctype_header.split(";", 1)[0].strip().lower()
    prefix = raw_bytes[: min(len(raw_bytes), 4096)].lstrip()
    pl = prefix.lower()
    looks_like_markup = pl.startswith(
        (
            b"<html",
            b"<!doctype",
            b"<head",
            b"<meta",
            b"<body",
            b"<div",
            b"<main",
            b"<article",
        )
    )
    sniff_meta = ("html" in ctype) or looks_like_markup
    text = _decode_http_body_bytes(raw_bytes, ctype_header, sniff_html_meta=sniff_meta)

    prefix_txt_l = text.lstrip()[:64].lower().strip("\ufeff")
    parse_as_html = ("html" in ctype and "javascript" not in ctype) or ("xml" in ctype and "svg" not in ctype)
    parse_as_html = parse_as_html or looks_like_markup
    parse_as_html = parse_as_html or prefix_txt_l.startswith(
        ("<html", "<!doctype", "<head", "<meta", "<body", "<?xml")
    )

    if parse_as_html:
        hostname = urlparse(safe_url).hostname or ""
        parser = _HtmlToTextParser()
        parser.feed(text)
        parser.close()
        body = _merge_html_visible_with_spa_fallback(text, parser.text())
        body = _apply_notion_body_enrichment(hostname, text, body)
        # 粗略取 <title>
        tm = re.search(r"<title[^>]*>([^<]+)</title>", text, re.I | re.DOTALL)
        title_hint = html.unescape(re.sub(r"\s+", " ", tm.group(1)).strip()) if tm else ""
        return title_hint, body or ""

    return "", text.strip()


def _docx_body_ordered_plain(doc: object) -> str:
    """按文档中出现的顺序导出段落与表格单元格文本，弥补仅读 paragraph 遗漏表格正文的问题。"""
    from docx.oxml.ns import qn  # type: ignore[import-untyped]
    from docx.table import Table  # type: ignore[import-untyped]
    from docx.text.paragraph import Paragraph  # type: ignore[import-untyped]

    lines: list[str] = []
    body = getattr(getattr(doc, "element", None), "body", None)
    if body is None:
        return ""

    def _kids():
        ich = getattr(body, "iterchildren", None)
        if callable(ich):
            try:
                return list(ich())
            except TypeError:
                pass
        try:
            return list(body)
        except TypeError:
            return []

    for child in _kids():
        tag = getattr(child, "tag", None)
        if tag == qn("w:p"):
            tx = (Paragraph(child, doc).text or "").strip()
            if tx:
                lines.append(tx)
        elif tag == qn("w:tbl"):
            tbl = Table(child, doc)
            try:
                for row in tbl.rows:
                    cells = []
                    for cell in row.cells:
                        cx = ((cell.text or "").replace("\t", " ")).strip()
                        if cx:
                            cells.append(cx.replace("\n", " "))
                    row_txt = " | ".join(cells).strip()
                    if row_txt:
                        lines.append(row_txt)
            except Exception:
                continue

    return "\n".join(lines).strip()


ALLOWED_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".html", ".htm", ".docx", ".pdf"})


def normalize_filename(filename: str) -> str:
    name = PurePosixPath(filename.split("/")[-1]).name.strip()
    if not name:
        name = "upload.bin"
    return name


def file_to_plain(filename: str, data: bytes) -> str:
    ext = PurePosixPath(filename.lower()).suffix
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的扩展名「{ext}」，允许：{', '.join(sorted(ALLOWED_EXTENSIONS))}")

    if ext in {".txt", ".md", ".markdown"}:
        return _decode_http_body_bytes(data, "", sniff_html_meta=False).strip()

    if ext in {".html", ".htm"}:
        t = _decode_http_body_bytes(data, "", sniff_html_meta=True)
        parser = _HtmlToTextParser()
        parser.feed(t)
        parser.close()
        body = _merge_html_visible_with_spa_fallback(t, parser.text()).strip()
        return body if body else t.strip()

    if ext == ".docx":
        try:
            from docx import Document  # type: ignore[import-untyped]

            doc = Document(BytesIO(data))
            merged = _docx_body_ordered_plain(doc)
            if merged:
                return merged
            return "\n".join((p.text or "").strip() for p in doc.paragraphs if (p.text or "").strip()).strip()
        except Exception as exc:
            raise ValueError(f"DOCX 解析失败：{exc}") from exc

    if ext == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore[import-untyped]

            reader = PdfReader(BytesIO(data))
            parts: list[str] = []
            total_chars = 0
            truncated = False
            for page in reader.pages:
                t = page.extract_text() or ""
                if not t.strip():
                    continue
                blk = t.strip()
                parts.append(blk)
                total_chars += len(blk)
                if total_chars >= _MAX_PDF_EXTRACT_CHARS:
                    truncated = True
                    break
            plain = "\n\n".join(parts).strip()
            if truncated:
                plain += "\n\n…（为避免超大 PDF 占用过多内存与上下文，仅在达到字符上限前的页面已导出；可按章节拆分或多条导入。）"
            return plain
        except Exception as exc:
            raise ValueError(f"PDF 解析失败：{exc}") from exc

    raise ValueError("未知文件类型")


def title_from_filename(filename: str) -> str:
    name = PurePosixPath(normalize_filename(filename)).stem.strip()
    return name or "未命名导入"


# ===================== 官方 API 导入（Notion 等平台） =====================

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"


def _notion_headers(api_key: str) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key:
        raise ValueError("Notion Integration Token 不能为空")
    return {
        "Authorization": f"Bearer {key}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }


def _notion_rich_text_to_md(rt: list[dict]) -> str:
    if not rt:
        return ""
    parts: list[str] = []
    for item in rt:
        text = item.get("plain_text") or (item.get("text") or {}).get("content", "")
        ann = item.get("annotations", {})
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if ann.get("strikethrough"):
            text = f"~~{text}~~"
        link = item.get("href") or (item.get("text") or {}).get("link", {}).get("url")
        if link:
            text = f"[{text}]({link})"
        parts.append(text)
    return "".join(parts)


def _notion_block_to_lines(block: dict, indent: int = 0) -> list[str]:
    t = block.get("type", "")
    val = block.get(t, {}) or {}
    prefix = "  " * indent
    lines: list[str] = []

    if t in ("paragraph", "heading_1", "heading_2", "heading_3"):
        text = _notion_rich_text_to_md(val.get("rich_text", []))
        if t == "heading_1":
            lines.append(f"# {text}")
        elif t == "heading_2":
            lines.append(f"## {text}")
        elif t == "heading_3":
            lines.append(f"### {text}")
        else:
            lines.append(text or "")

    elif t == "bulleted_list_item":
        text = _notion_rich_text_to_md(val.get("rich_text", []))
        lines.append(f"{prefix}- {text}")

    elif t == "numbered_list_item":
        text = _notion_rich_text_to_md(val.get("rich_text", []))
        lines.append(f"{prefix}1. {text}")

    elif t == "to_do":
        text = _notion_rich_text_to_md(val.get("rich_text", []))
        checked = "x" if val.get("checked") else " "
        lines.append(f"{prefix}- [{checked}] {text}")

    elif t == "code":
        lang = val.get("language", "")
        text = _notion_rich_text_to_md(val.get("rich_text", []))
        lines.append(f"```{lang}\n{text}\n```")

    elif t == "quote":
        text = _notion_rich_text_to_md(val.get("rich_text", []))
        lines.append(f"{prefix}> {text}")

    elif t == "divider":
        lines.append("---")

    elif t == "child_page":
        title = val.get("title", "")
        lines.append(f"📄 子页面：{title}")

    elif t == "table_of_contents":
        lines.append("[目录]")

    else:
        # 其他复杂块（table、embed、image、synced_block 等）先占位
        lines.append(f"{prefix}[未支持的 Notion 块类型: {t}]")

    return lines


def fetch_official_notion_page(api_key: str, page_id: str) -> tuple[str, str]:
    """
    使用 Notion 官方 API 获取单个 Page 的完整内容（含递归子块）。
    返回 (title, markdown_text)。
    """
    headers = _notion_headers(api_key)
    # 去掉可能的横线
    clean_id = page_id.replace("-", "")

    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        # 获取页面属性
        r = client.get(f"{NOTION_BASE}/pages/{clean_id}", headers=headers)
        r.raise_for_status()
        page = r.json()

        # 提取标题
        title = ""
        for p in (page.get("properties") or {}).values():
            if p.get("type") == "title":
                title = _notion_rich_text_to_md(p.get("title", []))
                break
        if not title:
            title = page.get("id", "Untitled Notion Page")

        # 递归拉取所有块
        all_blocks: list[dict] = []

        def fetch_children(block_id: str):
            cursor = None
            while True:
                params: dict[str, str | int] = {"page_size": 100}
                if cursor:
                    params["start_cursor"] = cursor
                rr = client.get(
                    f"{NOTION_BASE}/blocks/{block_id}/children",
                    headers=headers,
                    params=params,
                )
                rr.raise_for_status()
                data = rr.json()
                for b in data.get("results", []):
                    all_blocks.append(b)
                    if b.get("has_children"):
                        fetch_children(b["id"])
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")

        fetch_children(clean_id)

        # 转文本
        md_lines: list[str] = []
        for b in all_blocks:
            md_lines.extend(_notion_block_to_lines(b))

        body = "\n".join(md_lines).strip()
        return title, body or "(Notion 页面内容为空或无可读取块)"


def fetch_official_notion_database(
    api_key: str, db_id: str, max_pages: int = 30
) -> list[tuple[str, str]]:
    """
    拉取 Notion Database 中的多条页面（简单实现）。
    返回 [(title, body), ...] 列表。
    """
    headers = _notion_headers(api_key)
    clean_id = db_id.replace("-", "")
    results: list[tuple[str, str]] = []

    with httpx.Client(timeout=120.0) as client:
        cursor = None
        fetched = 0
        while fetched < max_pages:
            params: dict[str, str | int] = {"page_size": 10}
            if cursor:
                params["start_cursor"] = cursor
            r = client.post(
                f"{NOTION_BASE}/databases/{clean_id}/query",
                headers=headers,
                json=params,
            )
            r.raise_for_status()
            data = r.json()
            for page in data.get("results", []):
                pid = page.get("id", "")
                if not pid:
                    continue
                try:
                    t, b = fetch_official_notion_page(api_key, pid)
                    results.append((t, b))
                    fetched += 1
                    if fetched >= max_pages:
                        break
                except Exception:
                    continue
            if not data.get("has_more") or fetched >= max_pages:
                break
            cursor = data.get("next_cursor")

    return results


# ===================== Confluence Cloud（REST API） =====================


def fetch_official_confluence_page(domain: str, email: str, api_token: str, page_id: str) -> tuple[str, str]:
    """
    Atlassian Confluence Cloud：使用邮箱 + API Token（Basic）读取页面 storage HTML。
    domain 示例：yourcompany.atlassian.net（不要含 https:// 与路径）
    page_id：页面数字 ID（非 spaceKey~title 形式）。
    """
    dom = (domain or "").strip().lower().replace("https://", "").replace("http://", "").split("/")[0].rstrip(".")
    if not dom or "." not in dom:
        raise ValueError("Confluence 请填写有效的站点域名，例如 yourcompany.atlassian.net")
    em = (email or "").strip()
    tok = (api_token or "").strip()
    if not em or not tok:
        raise ValueError("Confluence 需要邮箱与 API Token")
    pid = (page_id or "").strip()
    if not pid.isdigit():
        raise ValueError("Confluence 页面 ID 须为数字（在页面 URL 的 /pages/123456789/... 中）")

    base = f"https://{dom}/wiki/rest/api/content/{pid}"
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        r = client.get(
            base,
            params={"expand": "body.storage,title,version"},
            auth=(em, tok),
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()

    title = (data.get("title") or "").strip() or f"Confluence Page {pid}"
    storage = (((data.get("body") or {}).get("storage")) or {}).get("value") or ""
    if not storage.strip():
        return title, "（Confluence 页面无 storage 正文或无权读取 body）"

    parser = _HtmlToTextParser()
    parser.feed(storage)
    parser.close()
    body = parser.text().strip() or storage
    return title, body


# ===================== 飞书 / Lark（开放平台） =====================

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"


def _feishu_tenant_access_token(app_id: str, app_secret: str) -> str:
    aid = (app_id or "").strip()
    sec = (app_secret or "").strip()
    if not aid or not sec:
        raise ValueError("飞书需要 app_id 与 app_secret（app_secret 可填在「API Key」栏）")
    with httpx.Client(timeout=45.0) as client:
        r = client.post(
            FEISHU_TOKEN_URL,
            json={"app_id": aid, "app_secret": sec},
        )
        r.raise_for_status()
        data = r.json()
    if int(data.get("code", -1)) != 0:
        raise ValueError(f"飞书获取 tenant_access_token 失败：{data.get('msg', data)}")
    token = (data.get("tenant_access_token") or "").strip()
    if not token:
        raise ValueError("飞书返回的 tenant_access_token 为空")
    return token


def _feishu_normalize_document_id(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("飞书文档 ID 不能为空")
    # 从 URL 提取 docx 文档 token
    m = re.search(r"/docx/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    m2 = re.search(r"(doxcn[A-Za-z0-9_-]+)", s)
    if m2:
        return m2.group(1)
    return s


def fetch_official_feishu_doc(app_id: str, app_secret: str, document_id: str) -> tuple[str, str]:
    """
    飞书云文档：使用自建应用 app_id + app_secret 换 tenant_access_token，再拉取 docx 纯文本（Markdown 近似）。
    document_id：文档 token（doxcn…）或含 /docx/ 的完整链接。
    需在飞书开放平台为应用开通「查看、编辑和管理云空间中所有文件」等 docx 相关权限。
    """
    doc_id = _feishu_normalize_document_id(document_id)
    token = _feishu_tenant_access_token(app_id, app_secret)
    raw_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/raw_content"
    meta_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}"
    with httpx.Client(timeout=90.0) as client:
        hdr = {"Authorization": f"Bearer {token}"}
        r = client.get(raw_url, headers=hdr)
        r.raise_for_status()
        data = r.json()
    if int(data.get("code", -1)) != 0:
        raise ValueError(f"飞书读取文档失败：{data.get('msg', data)}")
    inner = data.get("data") or {}
    content = (inner.get("content") or "").strip()
    title = (inner.get("title") or "").strip()
    if not title:
        with httpx.Client(timeout=45.0) as client:
            r2 = client.get(meta_url, headers={"Authorization": f"Bearer {token}"})
            r2.raise_for_status()
            d2 = r2.json()
        if int(d2.get("code", -1)) == 0:
            doc = (d2.get("data") or {}).get("document") or {}
            title = (doc.get("title") or "").strip()
    title = title or doc_id
    return title, content or "（飞书文档正文为空）"


# ===================== Obsidian Publish（无官方 REST，按公开页抓取） =====================


def fetch_official_obsidian_publish_page(publish_url: str) -> tuple[str, str]:
    """
    Obsidian 无面向第三方 vault 的官方 HTTP API；已发布站点使用 Obsidian Publish。
    此处将「完整发布页 URL」交给与普通网页相同的抓取管线，保证正文尽量完整。
    """
    u = (publish_url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        raise ValueError("Obsidian Publish 请填写以 http(s) 开头的完整页面 URL")
    host = (urlparse(u).hostname or "").lower()
    if not host:
        raise ValueError("无效的 Obsidian Publish URL")
    # 常见 publish 域名；自定义域名也允许，仅作弱提示
    if "obsidian.md" not in host and "publish.obsidian" not in host:
        pass  # 允许自定义发布域名
    return fetch_url_body(u)
