#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path as p
from typing import List, Optional, Tuple

# ----------------------------
# Regex
# ----------------------------

# 例: "## []", "## [w]"
HEADER_RE = re.compile(r"^## \[(?P<tag>.*?)\].*$")

# 例:
#   ## [] 2026/02/13 タスクA
#   ## [] 2026/02/13(月) タスクA
#   ## [] 2026/02/13(Fri) タスクA
HEADER_WITH_DATE_RE = re.compile(
    r"^(?P<prefix>## \[(?P<tag>.*?)\])\s*"
    r"(?P<date>\d{4}/\d{2}/\d{2})"
    r"(?:\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|月|火|水|木|金|土|日)\))?"
    r"\s*(?P<title>.*)$"
)

# 子の仕様（あなた指定の4パターンを狙い撃ち）
#   - [] 2026/02/19(Mon) ...
#   - [x] 2026/02/19(Tue) ...
#   - [] 2026/02/19(月) ...
#   - [x] 2026/02/19(日) ...
# ※空白揺れは少しだけ許容（- の後やカッコ前の空白）
CHILD_LINE_RE = re.compile(
    r"^(?P<indent>\s*)-\s*"
    r"\[(?P<check>x|X)?\]\s*"  # [] or [x]
    r"(?P<date>\d{4}/\d{2}/\d{2})\s*"
    r"(?P<wd>\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|月|火|水|木|金|土|日)\))"
    r"(?P<rest>.*)$"
)

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def _weekday_jp(date_str: str) -> Optional[str]:
    """YYYY/MM/DD -> '月'..'日'（失敗なら None）"""
    try:
        y, mo, d = date_str.split("/")
        return WEEKDAYS_JP[_date(int(y), int(mo), int(d)).weekday()]
    except Exception:
        return None


def _append_or_fix_weekday_jp(date_str: str) -> str:
    """YYYY/MM/DD -> YYYY/MM/DD(曜)。曜日は常に日付から正しい漢字で付け直す。"""
    wd = _weekday_jp(date_str)
    return f"{date_str}({wd})" if wd else date_str


def _normalize_child_line(line: str) -> Tuple[str, Optional[Tuple[bool, str]]]:
    """
    子行を正規化:
      - 形式: '- [] YYYY/MM/DD(曜) ...' / '- [x] YYYY/MM/DD(曜) ...'
      - 入力の曜日が英語でも漢字でも、出力は必ず「正しい漢字曜日」に上書き
    """
    s = line.rstrip("\n")
    m = CHILD_LINE_RE.match(s)
    if not m:
        return line, None

    indent = m.group("indent") or ""
    is_checked = (m.group("check") or "").lower() == "x"
    dt = m.group("date")
    rest = m.group("rest") or ""

    # 子の曜日は常に「日付から正しい漢字」に修正
    dt2 = _append_or_fix_weekday_jp(dt)

    # rest のスペース整形（"詳細" のように詰まってたら先頭にスペース）
    rest2 = rest
    if rest2 and not rest2.startswith(" "):
        rest2 = " " + rest2.lstrip()

    chk = "x" if is_checked else ""
    new_line = f"{indent}- [{chk}] {dt2}{rest2}"
    return new_line + ("\n" if line.endswith("\n") else ""), (is_checked, dt)


def _normalize_header_line(header_line: str) -> str:
    """
    ヘッダ行は漢字曜日で統一して付け直す（英語/誤り/無しを修正）
      ## [tag] YYYY/MM/DD(曜) タイトル
    """
    h = header_line.rstrip("\n")
    m = HEADER_WITH_DATE_RE.match(h)
    if not m:
        return header_line

    prefix = m.group("prefix")
    dt = m.group("date")
    title = m.group("title")

    dt2 = _append_or_fix_weekday_jp(dt)
    new_h = f"{prefix} {dt2} {title}".rstrip()
    return new_h + ("\n" if header_line.endswith("\n") else "")


@dataclass(frozen=True)
class Chunk:
    text: str

    @property
    def first_line(self) -> str:
        return self.text.splitlines()[0] if self.text else ""

    @property
    def is_header_chunk(self) -> bool:
        return self.first_line.startswith("## [")

    @property
    def tag(self) -> str | None:
        if not self.is_header_chunk:
            return None
        m = HEADER_RE.match(self.first_line)
        if not m:
            return None
        return m.group("tag").strip()

    def rewrite_header_date_from_children(self) -> "Chunk":
        """
        親日付の書き換え:
          - 子のうち [x] を除外
          - [] の中で最も早い日付を採用
          - [] が無ければ親は変更しない
        ついでに子行も正規化（曜日を正しい漢字へ）
        """
        if not self.is_header_chunk or not self.text:
            return self

        lines = self.text.splitlines(keepends=True)
        if not lines:
            return self

        header0 = lines[0]
        h = header0.rstrip("\n")
        mh = HEADER_WITH_DATE_RE.match(h)
        if not mh:
            # ヘッダが想定外でも、子だけは正規化して返す
            out = [header0]
            changed = False
            for line in lines[1:]:
                new_line, info = _normalize_child_line(line)
                if info is not None and new_line != line:
                    changed = True
                out.append(new_line if info is not None else line)
            return Chunk("".join(out)) if changed else self

        out_lines = [header0]
        unchecked_dates: List[str] = []

        for line in lines[1:]:
            new_line, info = _normalize_child_line(line)
            out_lines.append(new_line if info is not None else line)
            if info:
                is_checked, dt = info
                if not is_checked:
                    unchecked_dates.append(dt)

        if not unchecked_dates:
            return Chunk("".join(out_lines))

        chosen = min(unchecked_dates)

        prefix = mh.group("prefix")
        title = mh.group("title")
        new_header = f"{prefix} {chosen} {title}".rstrip()
        out_lines[0] = new_header + ("\n" if header0.endswith("\n") else "")
        return Chunk("".join(out_lines))

    def normalize_weekday(self) -> "Chunk":
        """ヘッダは漢字曜日で付け直し。子は正規化済みだが保険で再適用。"""
        if not self.text:
            return self

        lines = self.text.splitlines(keepends=True)
        if not lines:
            return self

        changed = False
        out: List[str] = []

        if self.is_header_chunk:
            new_header = _normalize_header_line(lines[0])
            if new_header != lines[0]:
                changed = True
            out.append(new_header)
            start_idx = 1
        else:
            start_idx = 0

        for line in lines[start_idx:]:
            new_line, info = _normalize_child_line(line)
            if info is not None and new_line != line:
                changed = True
            out.append(new_line if info is not None else line)

        return Chunk("".join(out)) if changed else self


class ChunkParser:
    def split(self, text: str) -> List[Chunk]:
        lines = text.splitlines(keepends=True)

        chunks: List[str] = []
        cur: List[str] = []

        def flush():
            nonlocal cur
            chunks.append("".join(cur))
            cur = []

        for line in lines:
            if line.startswith("## ["):
                if cur:
                    flush()
                cur.append(line)
            else:
                cur.append(line)

        if cur:
            flush()

        return [Chunk(t) for t in chunks] if chunks else [Chunk("")]


class ChunkOrganizer:
    def _preprocess_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        if not chunks:
            return [Chunk("")]

        head = chunks[0]
        rest = [
            c.rewrite_header_date_from_children().normalize_weekday()
            for c in chunks[1:]
        ]
        return [head] + rest

    def sort_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        chunks = self._preprocess_chunks(chunks)
        if not chunks:
            return [Chunk("")]

        head = chunks[0]
        rest = chunks[1:]

        chunk_void: List[Chunk] = []
        chunk_w: List[Chunk] = []
        chunk_others: List[Chunk] = []

        for c in rest:
            t = c.tag
            if t == "":
                chunk_void.append(c)
            elif t == "w":
                chunk_w.append(c)
            else:
                chunk_others.append(c)

        chunk_void.sort(key=lambda x: x.first_line, reverse=True)
        chunk_w.sort(key=lambda x: x.first_line, reverse=True)
        chunk_others.sort(key=lambda x: x.first_line, reverse=True)

        return [head] + chunk_void + chunk_w + chunk_others


class TextSorterApp:
    def __init__(self, tgtpath: str | p):
        self.tgtpath = p(tgtpath)
        self.parser = ChunkParser()
        self.organizer = ChunkOrganizer()

    def run(self) -> str:
        text = self.tgtpath.read_text(encoding="utf-8")
        chunks = self.parser.split(text)
        sorted_chunks = self.organizer.sort_chunks(chunks)
        return "".join(c.text for c in sorted_chunks)


def main():
    tgtpath = "mynote_sorter_sample.txt"  # ここを書き換え
    app = TextSorterApp(tgtpath)
    out = app.run()
    print(out, end="")

    out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")
    out_path.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
