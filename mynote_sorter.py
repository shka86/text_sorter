#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path as p
from typing import List, Optional, Tuple
from itertools import groupby

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
# class OutChunk():
#     def __init__(self,
#         p_status, p_date, p_title, c_body,
#         ):
#         self.p_status = p_status
#         self.p_date = p_date
#         self.p_title = p_title.rstrip()
#         self.c_body = c_body.rstrip()
#     def build_chunk(self):
#         self.chunk = f"## {self.p_status} {self.p_date} {self.p_title}\n{self.c_body}"
#         print(self.chunk)


class MyTask:
    def __init__(self, body):
        self.body = body
        self.split_chunks()

    def split_chunks(self):
        dlmt = r"(^## \[)"
        parts = re.split(dlmt, self.body, flags=re.MULTILINE)
        self.top_memo = parts[0].rstrip()
        chunks = [parts[i] + parts[i + 1] for i in range(1, len(parts), 2)]
        self.parents = [Parent(x) for x in chunks]

    def show(self):
        out = f"{self.top_memo}"
        print(f"--- {__class__.__name__} --------------------------------")
        print(out)
        print(f"--- {__class__.__name__} --------------------------------")
        [x.show() for x in self.parents]

    def parent_build(self):
        out = f"{self.top_memo}\n"
        for parent in self.parents:
            out += f"## {parent.status} {parent.date} {parent.title}\n{parent.top_memo}"
            for child in parent.childs:
                out += f"{child.out}\n"
        self.out = out
        return self.out

    def child_build(self):
        # 子タスク基準で並べて、
        # 区切り線になっている日曜日をいったん消して、open機関だけもう一度日曜日を入れる処理をする
        #
        out = f"{self.top_memo}\n"
        # all_childs = []
        # for parent in self.parents:
        #     out += f"## {parent.status} {parent.date} {parent.title}\n{parent.top_memo}"
        #     for child in parent.childs:
        #         all_childs.append(child)
        #         out += f"{child.out}\n"
        # self.out = out
        # return self.out


class Parent:
    def __init__(self, chunk):
        self.chunk = chunk
        self.parse()
        self.update_date()
        self.sort()

    def build(self):
        out = f"## {self.status} {self.date} {self.title}"
        if self.rest:
            out += f"\n{self.rest}"
        self.out = out

    def sort(self):
        open_childs = [x for x in self.childs if x.status == "[]"]
        open_childs = sorted(open_childs, key=lambda x: x.date)
        closed_childs = [x for x in self.childs if x.status == "[x]"]
        closed_childs = sorted(closed_childs, key=lambda x: x.date, reverse=True)
        self.childs = open_childs + closed_childs
        # self.out = "\n".join([x.out for x in childs])

    def update_date(self):
        open_childs = [x for x in self.childs if x.status == "[]"]
        open_childs.sort(key=lambda x: x.date)
        new_date = open_childs[0].date
        self.date = new_date

    def parse(self):
        lines = self.chunk.splitlines()
        topline = lines[0]
        ptn = r"^## (?P<status>\[.*\]) (?P<date>\d{4}/\d{2}/\d{2})(\([月火水木金土日]\))? (?P<title>.*)$"
        m = re.match(ptn, topline, flags=re.MULTILINE)
        self.status = m.group("status").rstrip()
        self.date = m.group("date").rstrip()
        self.date = fix_weekday_jp(self.date)
        self.title = m.group("title").rstrip()

        child = "\n".join(lines[1:]).rstrip()
        dlmt = r"(^- \[[x]?\] \d{4}/\d{2}/\d{2})"
        parts = re.split(dlmt, child, flags=re.MULTILINE)
        self.top_memo = parts[0].rstrip()
        chunks = [parts[i] + parts[i + 1] for i in range(1, len(parts), 2)]
        self.childs = [Child(x) for x in chunks]

    def show(self):
        out = f"## {self.status} {self.date} {self.title}\n{self.top_memo}"
        print(f"--- {__class__.__name__} --------------------------------")
        print(out)
        print(f"--- {__class__.__name__} --------------------------------")
        [x.show() for x in self.childs]


class Child:
    def __init__(self, chunk):
        self.chunk = chunk
        self.parse()
        self.build()

    def parse(self):
        ptn = r"^- (?P<status>\[[xi]?\]) (?P<date>\d{4}/\d{2}/\d{2})(\([月火水木金土日]\))? (?P<title>[^\n]*)(?:\n(?P<rest>[\s\S]*))?$"
        m = re.match(ptn, self.chunk, flags=re.DOTALL)
        if m:
            self.status = m.group("status").rstrip()
            self.date = m.group("date").rstrip()
            self.date = fix_weekday_jp(self.date)
            self.title = m.group("title").rstrip()
            raw_rest = m.group("rest")
            self.rest = raw_rest.rstrip() if raw_rest else None

    def build(self):
        out = f"- {self.status} {self.date} {self.title}"
        if self.rest:
            out += f"\n{self.rest}"
        self.out = out

    def show(self):
        print(f"--- {__class__.__name__} --------------------------------")
        # print(self.chunk)
        # print(self.status, self.date, self.title, self.rest)
        print(self.out)
        print(f"--- {__class__.__name__} --------------------------------")


def fix_weekday_jp(date_str: str) -> Optional[str]:
    try:
        y, mo, d = date_str.split("/")
        d = d[:2]  # 古い曜日を捨てる
        return f"{date_str}({WEEKDAYS_JP[_date(int(y), int(mo), int(d)).weekday()]})"
    except Exception:
        return date_str


def manage_sunday_chunks(tasks: List[MyTasks]) -> List[OutChunk]:
    # 1. 既存の日曜日チャンク（タイトルが "---"）を除外
    active_tasks = [x for x in tasks if x.p_title != "---"]
    if not active_tasks:
        return []

    # 2. 日付範囲の特定
    def to_date(s):
        return _date(*map(int, s.split("(")[0].split("/")))

    sorted_tasks = sorted(active_tasks, key=lambda x: x.c_date)
    first_d = to_date(sorted_tasks[0].c_date)
    last_d = to_date(sorted_tasks[-1].c_date)

    # 3. 日曜日チャンクの生成
    sundays = []
    # 最古日の「次の日曜日」を計算
    curr = first_d + _date.fromtimestamp(0).resolution * (
        7 - (first_d.weekday() + 1) % 7 or 7
    )
    # 最新日の「次の日曜日」まで作成
    end_d = last_d + _date.fromtimestamp(0).resolution * (
        7 - (last_d.weekday() + 1) % 7 or 7
    )

    import datetime

    delta = datetime.timedelta(days=7)
    tmp_curr = curr
    while tmp_curr <= end_d:
        d_str = tmp_curr.strftime("%Y/%m/%d")
        # 形式: ## [] yyyy/mm/dd(日) ---
        sundays.append(
            OutChunk("[]", f"{d_str}(日)", "-----------------------------------", "")
        )
        tmp_curr += delta

    return active_tasks, sundays


def main():
    tgtpath = "mynote_sorter_sample.txt"  # ここを書き換え
    body = p(tgtpath).read_text(encoding="utf-8")

    # --- ##チャンク分解 --------------------------------
    my_task = MyTask(body)
    # my_task.show()
    out = my_task.parent_build()
    # out = my_task.child_build()
    print(out)
    # my_task.child_build()
    # [x.build() for x in my_task.parents]
    # [x.build() for x in my_task.parents]

    # # --- タスク分解 --------------------------------
    # dlmt1 = r"(^## \[)"
    # parts = re.split(dlmt1, body, flags=re.MULTILINE)
    # chunks = [parts[i] + parts[i+1] for i in range(1, len(parts), 2)]
    # content_head = parts[0]

    # dlmt2 = r"(^- \[\] |^- \[x\] )"
    # tasks = []
    # for chunk in chunks:

    #     # 親階層情報
    #     _, p_status, p_date, p_title = chunk.splitlines()[0].split(" ", 3)

    #     # 子階層情報
    #     parts = re.split(dlmt2, chunk.split("\n", 1)[1], flags=re.MULTILINE)
    #     child_head = parts[0]
    #     childs = [child_head] + [parts[i] + parts[i+1] for i in range(1, len(parts), 2)]
    #     childs = [x if x.startswith("- ") else f"- {x}" for x in childs]
    #     for child in childs:
    #         try:
    #             _, c_status, c_date, c_title = child.split(" ", 3)
    #             c_body = f"- {c_status} {fix_weekday_jp(c_date)} {c_title}"
    #         except Exception:
    #             c_status = c_date = c_title = ""
    #             c_body = child.rstrip()

    #         tasks.append(
    #             MyTasks(
    #                 p_status, fix_weekday_jp(p_date), p_title,
    #                 c_status, fix_weekday_jp(c_date), c_title, c_body
    #             )
    #         )

    # # --- 仕分け・並び替え --------------------------------
    # if mode == "split":
    #     out_chunks = []

    #     # 1. 未完了タスク
    #     open_list = [x for x in tasks if x.c_status == "[]"]
    #     filtered_open, sunday_chunks = manage_sunday_chunks(open_list)
    #     out_chunks.extend(sunday_chunks)
    #     for t in filtered_open:
    #         c_body = f"{t.c_body}"
    #         out_chunks.append(OutChunk("[]", t.c_date, t.p_title, c_body.strip()))
    #     out_chunks.sort(key=lambda x: x.p_date, reverse=False)

    #     # 2. 完了タスク
    #     closed_tasks = [x for x in tasks if x.c_status != "[]"]
    #     closed_tasks.sort(key=lambda x: (x.p_title, x.c_date), reverse=False)
    #     for pt, group in groupby(closed_tasks, key=lambda x: x.p_title):
    #         group_list = list(group)
    #         new_p_status = "[x]"
    #         new_p_date = max(t.c_date for t in group_list)
    #         c_body_combined = "".join([f"{t.c_body}\n" for t in group_list])
    #         out_chunks.append(OutChunk(new_p_status, new_p_date, pt, c_body_combined.strip()))

    # else:
    #     # 親タスクでまとめる
    #     tasks.sort(key=lambda x: (x.p_title, x.c_date), reverse=True)
    #     out_chunks = []
    #     # p_title のみをキーにしてグループ化
    #     for pt, group in groupby(tasks, key=lambda x: x.p_title):
    #         group_list = list(group)
    #         group_list.sort(key=lambda x: x.c_date, reverse=True)

    #         # 子タスクの状態を分析
    #         open_children = [t for t in group_list if t.c_status == "[]"]
    #         closed_children = [t for t in group_list if t.c_status == "[x]"]

    #         if open_children:
    #             # 未完了がある場合：未完了の中で最も早い日
    #             new_p_status = "[]"
    #             new_p_date = min(t.c_date for t in open_children)
    #         else:
    #             # すべて完了している場合：[x]とし、完了の中で最も遅い日
    #             new_p_status = "[x]"
    #             new_p_date = max(t.c_date for t in closed_children) if closed_children else group_list[0].p_date

    #         c_body_combined = "".join([f"{t.c_body}\n" for t in group_list])
    #         out_chunks.append(OutChunk(new_p_status, new_p_date, pt, c_body_combined.strip()))

    # 出力文字列の作成
    # out_body = "".join([f"\n## {c.p_status} {c.p_date} {c.p_title}\n{c.c_body}\n" for c in out_chunks])
    # out = content_head + out_body

    # # out_path = p(tgtpath)
    out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")
    out_path.write_text(out, encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        mode = sys.argv[2]
    else:
        mode = "split"  # デフォルト

    main()
