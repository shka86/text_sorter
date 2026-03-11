#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path as p
from typing import List, Optional, Tuple
from itertools import groupby


DELIMITER_PARENT = r"(^## \[[x]?\] \d{4}/\d{2}/\d{2}\([月火水木金土日]\)? [^\n]*)"
DELIMITER_CHILD = r"(^- \[[x]?\] \d{4}/\d{2}/\d{2}\([月火水木金土日]\)? [^\n]*)"

PICKPTN_PARENT = r"(^## (?P<status>\[[x]?\]) (?P<date>\d{4}/\d{2}/\d{2}(?:\([月火水木金土日]\))?) (?P<title>.*))"
PICKPTN_CHILD = r"^- (?P<status>\[[x]?\]) (?P<date>\d{4}/\d{2}/\d{2}(?:\([月火水木金土日]\))?) (?P<title>[^\n]*)(?:\n(?P<rest>[\s\S]*))?$"

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]

SUNDAY = "-----------------------------------"


class MyTask:
    def __init__(self, body):
        self.body = body
        self.parse_chunks()

    def parse_chunks(self):
        parts = re.split(DELIMITER_PARENT, self.body, flags=re.MULTILINE)
        self.top_memo = parts[0].rstrip()
        chunks = [parts[i] + parts[i + 1] for i in range(1, len(parts), 2)]

        all_parents = [Parent(x) for x in chunks]
        all_parents.sort(key=lambda x: x.title, reverse=True)

        # parentの整理
        bind_parents = []
        for title, group in groupby(all_parents, key=lambda x: x.title):
            p_list = list(group)
            base = p_list[0]

            # 同じparentが複数の時の処理
            if len(p_list) > 1:
                for other in p_list[1:]:
                    base.childs.extend(other.childs)

            # top_memo
            top_memo = ""
            for pt in p_list:
                if len(pt.top_memo) > 0:
                    top_memo += f"{pt.top_memo}\n"
            base.top_memo = top_memo.rstrip("\n")

            # status更新
            if any(x.status == "[]" for x in base.childs):
                base.status = "[]"

            # 日付更新
            open_childs = [x for x in base.childs if x.status == "[]"]
            closed_childs = [x for x in base.childs if x.status == "[x]"]
            if open_childs:
                base.date = min(c.date for c in open_childs)
            elif closed_childs:
                base.date = max(c.date for c in closed_childs)

            # 再ソート
            base.sort()
            bind_parents.append(base)
        self.parents = bind_parents

    def parent_root_build(self):
        out = f"{self.top_memo}\n"
        open_parents = [x for x in self.parents if x.status == "[]"]
        open_parents = sorted(open_parents, key=lambda x: x.date)
        closed_parents = [x for x in self.parents if x.status == "[x]"]
        closed_parents = sorted(closed_parents, key=lambda x: x.date, reverse=True)
        parents = open_parents + closed_parents
        for parent in parents:
            out += f"## {parent.status} {parent.date} {parent.title}"
            out += f"\n"
            if len(parent.top_memo) > 1:
                out += f"{parent.top_memo}\n"

            open_childs = [x for x in parent.childs if x.status == "[]"]
            open_childs = sorted(open_childs, key=lambda x: x.date, reverse=True)
            closed_childs = [x for x in parent.childs if x.status == "[x]"]
            closed_childs = sorted(closed_childs, key=lambda x: x.date, reverse=True)
            childs = open_childs + closed_childs
            for child in childs:
                out += f"{child.out}\n"
        self.out = out
        return self.out

    def child_root_build(self):
        out = f"{self.top_memo}\n"

        # --- open part --------------------------------
        for parent in self.parents:
            open_childs = [x for x in parent.childs if x.status == "[]"]
            open_childs = sorted(open_childs, key=lambda x: x.date)

            for child in open_childs:
                out += f"## [] {child.date} {parent.title}\n"
                out += f"{child.out}\n\n"

        # --- closed part --------------------------------
        for parent in self.parents:
            out += f"## [x] {parent.closeddate} {parent.title}"
            out += f"\n"

            if len(parent.top_memo) > 1:
                out += f"{parent.top_memo}\n"

            closed_childs = [x for x in parent.childs if x.status == "[x]"]
            closed_childs = sorted(closed_childs, key=lambda x: x.date, reverse=True)
            for child in closed_childs:
                out += f"{child.out}\n"

        self.out = out
        return self.out


class Parent:
    def __init__(self, chunk):
        self.chunk = chunk
        self.parse()
        self.update_date()
        self.sort()

    def parse(self):
        lines = self.chunk.splitlines()
        topline = lines[0]
        m = re.match(PICKPTN_PARENT, topline, flags=re.MULTILINE)
        self.status = m.group("status").rstrip()
        self.date = m.group("date").rstrip()
        self.date = fix_weekday_jp(self.date)
        self.title = m.group("title").rstrip()
        self.opendate = self.closeddate = self.date

        child = "\n".join(lines[1:]).rstrip()
        parts = re.split(DELIMITER_CHILD, child, flags=re.MULTILINE)
        self.top_memo = parts[0].rstrip()
        chunks = [parts[i] + parts[i + 1] for i in range(1, len(parts), 2)]
        self.childs = [Child(x, self) for x in chunks]

    def update_date(self):
        open_childs = [x for x in self.childs if x.status == "[]"]
        if len(open_childs) > 1:
            open_childs.sort(key=lambda x: x.date)
            new_date = open_childs[0].date
            self.date = new_date
            self.opendate = new_date

        closed_childs = [x for x in self.childs if x.status == "[x]"]
        if len(closed_childs) > 1:
            closed_childs.sort(key=lambda x: x.date)
            new_date = closed_childs[0].date
            self.closeddate = new_date

    def sort(self):
        open_childs = [x for x in self.childs if x.status == "[]"]
        open_childs = sorted(open_childs, key=lambda x: x.date)
        closed_childs = [x for x in self.childs if x.status == "[x]"]
        closed_childs = sorted(closed_childs, key=lambda x: x.date, reverse=True)
        self.childs = open_childs + closed_childs
        # self.out = "\n".join([x.out for x in childs])

    def build(self):
        out = f"## {self.status} {self.date} {self.title}"
        if self.rest:
            out += f"\n{self.rest}"
        self.out = out


class Child:
    def __init__(self, chunk, parent: Parent):
        self.chunk = chunk
        self.parent = parent
        self.parse()
        self.build()

    def parse(self):
        m = re.match(PICKPTN_CHILD, self.chunk, flags=re.DOTALL)
        if m:
            self.status = m.group("status").rstrip()
            self.date = m.group("date").rstrip()
            self.date = fix_weekday_jp(self.date)
            self.title = m.group("title").rstrip()
            raw_rest = m.group("rest")
            self.rest = raw_rest.rstrip("\n") if raw_rest else None
        else:
            print(self.chunk)
            pass

    def build(self):
        out = f"- {self.status} {self.date} {self.title}"
        if self.rest:
            out += f"\n{self.rest}"
        self.out = out.rstrip("\n")


def fix_weekday_jp(date_str: str) -> Optional[str]:
    try:
        y, mo, d = date_str.split("/")
        d = d[:2]  # 古い曜日を捨てる
        return f"{y}/{mo}/{d}({WEEKDAYS_JP[_date(int(y), int(mo), int(d)).weekday()]})"
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
    curr = first_d + _date.fromtimestamp(0).resolution * (7 - (first_d.weekday() + 1) % 7 or 7)
    # 最新日の「次の日曜日」まで作成
    end_d = last_d + _date.fromtimestamp(0).resolution * (7 - (last_d.weekday() + 1) % 7 or 7)

    import datetime

    delta = datetime.timedelta(days=7)
    tmp_curr = curr
    while tmp_curr <= end_d:
        d_str = tmp_curr.strftime("%Y/%m/%d")
        # 形式: ## [] yyyy/mm/dd(日) ---
        sundays.append(OutChunk("[]", f"{d_str}(日)", "-----------------------------------", ""))
        tmp_curr += delta

    return active_tasks, sundays


def main(mode):
    tgtpath = "mynote_sorter_sample.txt"  # ここを書き換え
    body = p(tgtpath).read_text(encoding="utf-8")

    my_task = MyTask(body)

    # -----------------------------------
    if mode == "default":
        out1 = my_task.parent_root_build()
        # # out_path = p(tgtpath)
        out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")
        out_path.write_text(out1, encoding="utf-8")
        print(count_nonspace(body))
        print(count_nonspace(out1))

    # -----------------------------------
    if mode == "open_split":
        out2 = my_task.child_root_build()
        # # out_path = p(tgtpath)
        out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted_split.txt")
        out_path.write_text(out2, encoding="utf-8")
        print(count_nonspace(body))
        print(count_nonspace(out2))


def count_nonspace(text):
    return len(text.replace(" ", "").replace("\n", "").replace("\t", ""))


if __name__ == "__main__":
    if len(sys.argv) > 2:
        mode = sys.argv[2]
    else:
        mode = "default"  # デフォルト

    main(mode)
