#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path as p
from typing import List, Optional

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
    r"(?:\s*(?P<wd>\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|月|火|水|木|金|土|日)\)))?"
    r"\s*(?P<title>.*)$"
)

# 例（新仕様の子）:
#   - [] 2026/02/19 ...
#   - [x] 2026/02/19 ...
# さらに入力揺れ許容:
#   - 2026/02/19 ...
#   - [] 2026/02/19(Mon) ...
#   - [x] 2026/02/19 (Tue) ...
CHILD_LINE_RE = re.compile(
    r"^(?P<indent>\s*)-\s*"
    r"(?:(?:\[(?P<check>[xX ]?)\])\s*)?"  # [] / [x] / [ ] / 無し
    r"(?P<date>\d{4}/\d{2}/\d{2})"
    r"(?:\s*(?P<wd>\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun|月|火|水|木|金|土|日)\)))?"
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


def _append_or_fix_weekday(date_str: str) -> str:
    """YYYY/MM/DD -> YYYY/MM/DD(曜)。曜日は常に日付から正しい(漢字)で付け直す。"""
    wd = _weekday_jp(date_str)
    return f"{date_str}({wd})" if wd else date_str


def _normalize_child_line(line: str) -> tuple[str, Optional[tuple[bool, str]]]:
    """
    子行を正規化して返す。
      - 形式を '- [] YYYY/MM/DD(曜) ...' / '- [x] YYYY/MM/DD(曜) ...' に統一
      - 英語曜日も漢字に
      - 曜日が誤っていても日付から修正
    戻り値:
      (新しい行, (is_checked, ymd) or None)
    """
    s = line.rstrip("\n")
    m = CHILD_LINE_RE.match(s)
    if not m:
        return line, None

    indent = m.group("indent") or ""
    check_raw = (m.group("check") or "").strip()
    is_checked = check_raw.lower() == "x"
    dt = m.group("date")
    rest = m.group("rest") or ""

    # 出力は必ず [] / [x]
    check_out = "x" if is_checked else ""

    # 曜日は必ず正しい漢字を付け直す
    dt2 = _append_or_fix_weekday(dt)

    # rest のスペース整形（"詳細" のように詰まってたら先頭にスペース）
    rest2 = rest
    if rest2 and not rest2.startswith(" "):
        rest2 = " " + rest2.lstrip()

    new_line = f"{indent}- [{check_out}] {dt2}{rest2}"
    return new_line + ("\n" if line.endswith("\n") else ""), (is_checked, dt)


def _normalize_header_line(header_line: str) -> str:
    """
    ヘッダ行:
      ## [tag] YYYY/MM/DD(曜) タイトル
    に統一（曜日は常に日付から正しい漢字で付け直す）
    """
    h = header_line.rstrip("\n")
    m = HEADER_WITH_DATE_RE.match(h)
    if not m:
        return header_line

    prefix = m.group("prefix")
    dt = m.group("date")
    title = m.group("title")

    dt2 = _append_or_fix_weekday(dt)
    new_h = f"{prefix} {dt2} {title}".rstrip()
    return new_h + ("\n" if header_line.endswith("\n") else "")


@dataclass(frozen=True)
class Chunk:
    """テキストの分割単位。先頭行が '## [' で始まる chunk は header_chunk 扱い。"""

    text: str

    @property
    def first_line(self) -> str:
        return self.text.splitlines()[0] if self.text else ""

    @property
    def is_header_chunk(self) -> bool:
        return self.first_line.startswith("## [")

    @property
    def tag(self) -> str | None:
        """'## []' -> '' / '## [w]' -> 'w' / headerでなければ None"""
        if not self.is_header_chunk:
            return None
        m = HEADER_RE.match(self.first_line)
        if not m:
            return None
        return m.group("tag").strip()

    def rewrite_header_date_from_children(self) -> "Chunk":
        """
        新ルール:
          親日付は、子日付のうち
            - [x] を除外し
            - - [] の中で最も早い日付
          を採用して YYYY/MM/DD を差し替える（曜日は後段で付け直す）
          - - [] が無い場合は親は変更しない
        ついでに子行も正規化する（曜日修正・英語→漢字・形式統一）
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
            # ヘッダの形式が想定外なら、子だけ正規化して返す
            out = [header0]
            changed = False
            for line in lines[1:]:
                new_line, _ = _normalize_child_line(line)
                if new_line != line:
                    changed = True
                out.append(new_line)
            return Chunk("".join(out)) if changed else self

        # 子行正規化しつつ、未完了日のみ収集
        out_lines = [header0]
        unchecked_dates: List[str] = []

        for line in lines[1:]:
            new_line, info = _normalize_child_line(line)
            out_lines.append(new_line)
            if info:
                is_checked, dt = info
                if not is_checked:
                    unchecked_dates.append(dt)

        if not unchecked_dates:
            # 親日付は変更しない（子の正規化は反映済み）
            return Chunk("".join(out_lines))

        chosen = min(unchecked_dates)

        # 親の YYYY/MM/DD を差し替え（曜日は normalize_weekday で付け直す）
        prefix = mh.group("prefix")
        title = mh.group("title")
        new_header = f"{prefix} {chosen} {title}".rstrip()
        out_lines[0] = new_header + ("\n" if header0.endswith("\n") else "")

        return Chunk("".join(out_lines))

    def normalize_weekday(self) -> "Chunk":
        """
        ヘッダ(##)と子(-)の日付に曜日を付け直す（誤り/英語/無しを修正）。
        子は rewrite_header_date_from_children でも正規化されるが、
        ここでもう一度かけて保険にする。
        """
        if not self.text:
            return self

        lines = self.text.splitlines(keepends=True)
        if not lines:
            return self

        changed = False
        out: List[str] = []

        # ヘッダ
        if self.is_header_chunk:
            new_header = _normalize_header_line(lines[0])
            if new_header != lines[0]:
                changed = True
            out.append(new_header)
            start_idx = 1
        else:
            start_idx = 0

        # 子
        for line in lines[start_idx:]:
            new_line, info = _normalize_child_line(line)
            if info is not None and new_line != line:
                changed = True
            out.append(new_line if info is not None else line)

        return Chunk("".join(out)) if changed else self


class ChunkParser:
    """'## [' で始まる行を境界として chunk 化する。"""

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

        # 仕様: 1chunk目は '## [' で始まらない文字列（空でもあり得る）
        return [Chunk(t) for t in chunks] if chunks else [Chunk("")]


class ChunkOrganizer:
    def _preprocess_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        ソート前の前処理（新仕様）:

        1) 子行を '- [] YYYY/MM/DD(曜)' / '- [x] YYYY/MM/DD(曜)' に正規化
           - 英語曜日→漢字
           - 誤曜日も日付から修正
        2) 親日付(##)を「未完了(- [])の最小日付」に書き換え（未完了なしなら変更しない）
        3) 親(##)の曜日も日付から正しい漢字に付け直す
        """
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
            t = c.tag  # "## []" -> "" / '## [w]' -> 'w'
            if t == "":
                chunk_void.append(c)
            elif t == "w":
                chunk_w.append(c)
            else:
                chunk_others.append(c)

        # 既存仕様: ヘッダ行（first_line）で文字列ソート（降順）
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
