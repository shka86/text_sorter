#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path as p
from typing import List

HEADER_RE = re.compile(r"^## \[(?P<tag>.*?)\].*$")  # 例: "## []", "## [w]"

# 例: "## [] 2026/02/13 タスクA"
HEADER_WITH_DATE_RE = re.compile(
    r"^(?P<prefix>## \[(?P<tag>.*?)\])\s*(?P<date>\d{4}/\d{2}/\d{2})\s*(?P<title>.*)$"
)

# 例: "- 2026/02/16 詳細めも"
CHILD_DATE_RE = re.compile(r"^\s*-\s*(?P<date>\d{4}/\d{2}/\d{2})\b")


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
        """
        拡張用:
          - '## []' なら "" (空文字)
          - '## [w]' なら "w"
          - ヘッダでない chunk は None
        """
        if not self.is_header_chunk:
            return None
        m = HEADER_RE.match(self.first_line)
        return m.group("tag") if m else None

    def rewrite_header_date_from_first_child(self) -> "Chunk":
        """2階層構造を想定し、ヘッダ(##)の日付を、直下(-)の先頭日付に置き換える。

        期待する形:
          ## [tag] YYYY/MM/DD タイトル
          - YYYY/MM/DD ...

        ルール:
          - chunk がヘッダでない / ヘッダに日付がない / 子に日付がない場合は変更しない
          - 子の日付は "最初に現れた - 行" を採用する（最小/最大ではない）
        """
        if not self.is_header_chunk:
            return self

        lines = self.text.splitlines(keepends=True)
        if not lines:
            return self

        m = HEADER_WITH_DATE_RE.match(lines[0].rstrip("\n"))
        if not m:
            return self

        child_date: str | None = None
        for line in lines[1:]:
            m2 = CHILD_DATE_RE.match(line)
            if m2:
                child_date = m2.group("date")
                break

        if not child_date:
            return self

        prefix = m.group("prefix")
        title = m.group("title")
        new_header = f"{prefix} {child_date} {title}".rstrip() + "\n"

        if new_header == lines[0]:
            return self

        return Chunk(new_header + "".join(lines[1:]))


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

        - 2階層構造のとき、## 階層の日付を - 階層の先頭日付に書き換える。
        """
        if not chunks:
            return [Chunk("")]
        head = chunks[0]
        rest = [c.rewrite_header_date_from_first_child() for c in chunks[1:]]
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

    out_path = p(tgtpath)  # 上書き保存
    # out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")  # 別名保存
    out_path.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
