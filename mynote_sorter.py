#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path as p
from typing import List

HEADER_RE = re.compile(r"^## \[(?P<tag>.*?)\].*$")  # 例: "## []", "## [w]"


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
    def sort_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
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

    out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")
    out_path.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
