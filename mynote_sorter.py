#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path as p
from typing import List

# 例: "## []", "## [w]"
HEADER_RE = re.compile(r"^## \[(?P<tag>.*?)\].*$")

# 例: "## [] 2026/02/13 タスクA" / "## [] 2026/02/13(月) タスクA"
HEADER_WITH_DATE_RE = re.compile(
    r"^(?P<prefix>## \[(?P<tag>.*?)\])\s*(?P<date>\d{4}/\d{2}/\d{2})(?:\([月火水木金土日]\))?\s*(?P<title>.*)$"
)

# 例: "- 2026/02/16 詳細めも" / "- 2026/02/16(月) 詳細めも"
CHILD_DATE_RE = re.compile(
    r"^(?P<indent>\s*-\s*)(?P<date>\d{4}/\d{2}/\d{2})(?P<wd>\([月火水木金土日]\))?(?P<rest>.*)$"
)

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def _append_weekday(date_str: str) -> str:
    """YYYY/MM/DD -> YYYY/MM/DD(曜)。既に曜日が付いていればそのまま。"""
    # 呼び出し側で "(曜)" を除いた日付が来る想定
    try:
        y, mo, d = date_str.split("/")
        wd = WEEKDAYS_JP[_date(int(y), int(mo), int(d)).weekday()]
        return f"{date_str}({wd})"
    except Exception:
        return date_str


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
        # "## [ ]" も空扱いにしたいので strip() して正規化
        return m.group("tag").strip()

    def rewrite_header_date_from_first_child(self) -> "Chunk":
        """2階層構造を想定し、ヘッダ(##)の日付を、直下(-)の先頭日付に置き換える。

        期待する形:
          ## [tag] YYYY/MM/DD(曜?) タイトル
          - YYYY/MM/DD(曜?) ...

        ルール:
          - chunk がヘッダでない / ヘッダに日付がない / 子に日付がない場合は変更しない
          - 子の日付は「最初に現れた - 行」を採用する（最小/最大ではない）
        """
        if not self.is_header_chunk or not self.text:
            return self

        lines = self.text.splitlines(keepends=True)
        if not lines:
            return self

        header = lines[0].rstrip("\n")
        mh = HEADER_WITH_DATE_RE.match(header)
        if not mh:
            return self

        child_date: str | None = None
        for line in lines[1:]:
            mc = CHILD_DATE_RE.match(line.rstrip("\n"))
            if mc:
                child_date = mc.group("date")  # "(曜)" は無視
                break

        if not child_date:
            return self

        prefix = mh.group("prefix")
        title = mh.group("title")
        # ここでは曜日は付けない（後段の normalize_weekday で付ける）
        new_header = f"{prefix} {child_date} {title}".rstrip() + "\n"

        if new_header == lines[0]:
            return self
        return Chunk(new_header + "".join(lines[1:]))

    def normalize_weekday(self) -> "Chunk":
        """ヘッダ(##)行と子(-)行の日付に曜日を付ける。すでに付いていれば何もしない。"""
        if not self.text:
            return self

        lines = self.text.splitlines(keepends=True)
        changed = False
        out: List[str] = []

        # ヘッダ(先頭行)
        if self.is_header_chunk and lines:
            header = lines[0].rstrip("\n")
            mh = HEADER_WITH_DATE_RE.match(header)
            if mh:
                prefix = mh.group("prefix")
                dt = mh.group("date")
                title = mh.group("title")
                # すでに曜日がついているか（正規表現側で許容してるので、元文字列から判定）
                if re.search(rf"{re.escape(dt)}\([月火水木金土日]\)", header) is None:
                    dt2 = _append_weekday(dt)
                    new_header = f"{prefix} {dt2} {title}".rstrip()
                    if new_header != header:
                        out.append(new_header + "\n")
                        changed = True
                    else:
                        out.append(lines[0])
                else:
                    out.append(lines[0])
            else:
                out.append(lines[0])
            start_idx = 1
        else:
            start_idx = 0

        # 子(-)行
        for line in lines[start_idx:]:
            s = line.rstrip("\n")
            mc = CHILD_DATE_RE.match(s)
            if mc:
                indent = mc.group("indent")
                dt = mc.group("date")
                wd = mc.group("wd")
                rest = mc.group("rest")
                if wd:
                    out.append(line)
                else:
                    dt2 = _append_weekday(dt)
                    out.append(f"{indent}{dt2}{rest}\n")
                    changed = True
            else:
                out.append(line)

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
        """ソート前の前処理。

        1) 2階層構造のとき、## 階層の日付を - 階層の先頭日付に書き換える
        2) ヘッダ(##)行と子(-)行の日付に曜日を付ける（YYYY/MM/DD -> YYYY/MM/DD(曜)）
        """
        if not chunks:
            return [Chunk("")]

        head = chunks[0]
        rest = [
            c.rewrite_header_date_from_first_child().normalize_weekday()
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
            t = c.tag  # "## []" -> "" / "## [w]" -> "w" / headerでなければ None
            if t == "":
                chunk_void.append(c)
            elif t == "w":
                chunk_w.append(c)
            else:
                chunk_others.append(c)

        # 既存仕様: ヘッダ行（first_line）で文字列ソート
        chunk_void.sort(key=lambda x: x.first_line)
        chunk_w.sort(key=lambda x: x.first_line)
        chunk_others.sort(key=lambda x: x.first_line)

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
    # 必要ならここで tgtpath を指定して実行
    tgtpath = "mynote_sorter_sample.txt"  # ここを書き換え
    app = TextSorterApp(tgtpath)
    out = app.run()
    print(out, end="")

    out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")
    out_path.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
