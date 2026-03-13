#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path as p
from typing import List, Optional, Tuple
from itertools import groupby
from datetime import timedelta

# \s* を使わず、データの通りに「スペース1つ」を厳格に指定
# 末尾に \n を入れないことで、最終行や改行コードの差異に強くします
DELIMITER_PARENT = r"(^## \[[x ]?\] \d{4}/\d{2}/\d{2}(?:\([月火水木金土日]\))? .+$)"
DELIMITER_CHILD = r"(^- \[[x ]?\] \d{4}/\d{2}/\d{2}(?:\((?:[月火水木金土日]|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\))? .+$)"

# 抽出用（PICKPTN）は、タイトルを確実に取るために [^\n]+ を使用
PICKPTN_PARENT = r"^## (?P<status>\[[x ]?\]) (?P<date>\d{4}/\d{2}/\d{2}(?:\([月火水木金土日]\))?) (?P<title>.+)"
PICKPTN_CHILD = (
    r"^- (?P<status>\[[x ]?\]) (?P<date>\d{4}/\d{2}/\d{2}(?:\((?:[月火水木金土日]|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\))?) (?P<title>[^\n]+)(?:\n(?P<rest>[\s\S]*))?$"
)

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
        all_parents = del_sunday(all_parents)
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

        # 未完了子タスクの一括集約
        all_open = []
        for parent in self.parents:
            if parent.title != SUNDAY:
                all_open.extend([c for c in parent.childs if c.status == "[]"])

        # 未完了パート：日付順にバラして出力
        if all_open:
            all_open = add_sunday(all_open)
            all_open.sort(key=lambda x: x.date)
            for child in all_open:
                if child.parent.title == SUNDAY:
                    out += f"## [] {child.date} {child.parent.title}\n\n"
                else:
                    out += f"## [] {child.date} {child.parent.title}\n{child.out}\n\n"

        # 完了パート、その他パート：親タスク（Parent）ごとにまとめて出力
        closed_parents = [parent for parent in self.parents if any(c.status != "[]" for c in parent.childs)]
        for parent in closed_parents:
            parent.date = max(x.date for x in [y for y in parent.childs if y.status != "[]"])
        closed_parents.sort(key=lambda x: x.date, reverse=True)

        for parent in closed_parents:
            out += f"## [x] {parent.date} {parent.title}\n"
            if parent.top_memo:
                out += f"{parent.top_memo}\n"

            for child in parent.childs:
                if child.status == "[x]":
                    out += f"{child.out}\n"
            out += "\n"

        self.out = out
        return self.out


def add_sunday(open_childs: List[Child]) -> List[Child]:
    if not open_childs:
        return []

    to_d = lambda s: _date(*map(int, s.split("(")[0].split("/")))
    cur = to_d(min(x.date for x in open_childs))
    end = to_d(max(x.date for x in open_childs))
    cur += timedelta(days=(6 - cur.weekday()))

    sundays = []
    while cur <= end:
        d_str = fix_weekday_jp(cur.strftime("%Y/%m/%d"))

        # 日曜日の親子
        p_sun = Parent(f"## [] {d_str} {SUNDAY}\n")
        c_sun = Child(f"- [] {d_str} {SUNDAY}", p_sun)
        sundays.append(c_sun)
        cur += timedelta(days=7)

    return open_childs + sundays


def del_sunday(tasks):
    return [x for x in tasks if x.title != SUNDAY]


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
        if len(chunks) == 0:
            self.childs = [Child("", self)]
        else:
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
        closed_childs = [x for x in self.childs if x.status == "[x]" or x.status == "DUMMYCHILD"]
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
            self.status = "DUMMYCHILD"
            self.date = fix_weekday_jp(self.parent.date)
            self.title = "DUMMYCHILD"
            raw_rest = self.chunk
            self.rest = raw_rest.rstrip("\n") if raw_rest else None

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
    # tgtpath = "mynote_sorter_sample_sorted.txt"  # ここを書き換え
    # tgtpath = "mynote_sorter_sample_sorted_split.txt"  # ここを書き換え
    body = p(tgtpath).read_text(encoding="utf-8")
    print(body)

    my_task = MyTask(body)

    # -----------------------------------
    if mode == "default":
        out1 = my_task.parent_root_build()
        # # out_path = p(tgtpath)
        out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted.txt")
        out_path.write_text(out1, encoding="utf-8")
        print(str(out_path))
        print(count_nonspace(body))
        print(count_nonspace(out1))

    # -----------------------------------
    if mode == "open_split":
        out2 = my_task.child_root_build()
        # # out_path = p(tgtpath)
        out_path = p(tgtpath).with_name(f"{p(tgtpath).stem}_sorted_split.txt")
        out_path.write_text(out2, encoding="utf-8")
        print(str(out_path))
        print(count_nonspace(body))
        print(count_nonspace(out2))

    print(mode)


def count_nonspace(text):
    return len(text.replace(" ", "").replace("\n", "").replace("\t", ""))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "default"  # デフォルト

    main(mode)
