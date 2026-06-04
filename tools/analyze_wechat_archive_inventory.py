#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re


SENSITIVE_PATTERNS = {
    "身份/证件": ("身份证", "护照", "港澳", "签证", "户口", "驾驶证"),
    "合同/协议": ("合同", "协议", "补充协议", "签约", "签字", "盖章", "章程"),
    "财务/票据": ("发票", "报销", "付款", "收款", "回款", "银行", "账单", "流水", "工资", "薪酬", "奖金"),
    "股权/治理": ("股权", "股东", "董事", "监事", "工商", "营业执照", "章程"),
    "人事/简历": ("简历", "录用", "offer", "背调", "离职", "入职", "绩效"),
    "医疗/健康": ("病历", "处方", "体检", "诊断", "医保", "医疗", "健康"),
}

TOPIC_PATTERNS = {
    "新能源物流": ("新能源", "物流", "换电", "重卡", "牵引车", "电动集卡", "煤矿运输"),
    "接待方案": ("接待方案", "来访", "接待", "行程"),
    "农牧食品": ("畜牧", "饲料", "养殖", "食品"),
    "AI/智能体": ("AI", "智能体", "Agent", "大模型", "训推", "算力"),
    "医疗健康": ("医疗", "医院", "健康", "诊后", "HIV", "病历"),
    "投资/商业计划": ("商业计划", "BP", "融资", "投资", "路演", "估值", "资本"),
    "会议/拜访/名单": ("会议", "纪要", "拜访", "名单", "议程", "回执", "座谈会"),
    "公司/产品介绍": ("公司介绍", "产品介绍", "业务介绍", "解决方案", "汇报材料"),
    "财务/报表/测算": ("财务", "报表", "测算", "成本", "预算", "费用"),
}

DOC_EXTENSIONS = {"pdf", "doc", "docx", "wps", "pages"}
SHEET_EXTENSIONS = {"xls", "xlsx", "csv"}
SLIDE_EXTENSIONS = {"ppt", "pptx"}
TEXT_EXTENSIONS = {"txt", "md", "html"}
MEDIA_EXTENSIONS = {"mp4", "mp3", "m4a", "aac", "ogg", "jpg", "jpeg", "png"}
ARCHIVE_EXTENSIONS = {"zip", "rar"}
BACKUP_FILENAMES = {"Backup.db", "Backup.db-backup", "Backup.db-shm", "Backup.db-wal"}


@dataclass(frozen=True)
class FileItem:
    path: Path
    size: int
    modified: datetime | None


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze WeChat archive files by metadata only.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "微信归档",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path.home()
        / "Library"
        / "Mobile Documents"
        / "com~apple~CloudDocs"
        / "微信归档"
        / "聊天文件-全量-2026-05-11"
        / "manifest-all.tsv",
    )
    parser.add_argument("--out", type=Path, default=Path("reports") / "wechat-archive-file-analysis.md")
    parser.add_argument("--index-out", type=Path, default=Path("reports") / "wechat-archive-file-index.csv")
    args = parser.parse_args()

    root = args.root.expanduser()
    manifest = args.manifest.expanduser()
    files = list(iter_files(root))
    manifest_rows = read_manifest_rows(manifest)
    report = render_report(root=root, manifest=manifest, files=files, manifest_rows=manifest_rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    write_index(args.index_out, root=root, files=files)
    print(f"wrote {args.out}")
    print(f"wrote {args.index_out}")
    return 0


def iter_files(root: Path) -> list[FileItem]:
    result: list[FileItem] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        try:
            modified = datetime.fromtimestamp(stat.st_mtime).astimezone()
        except (OSError, OverflowError, ValueError):
            modified = None
        result.append(FileItem(path=path, size=stat.st_size, modified=modified))
    return result


def read_manifest_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def render_report(*, root: Path, manifest: Path, files: list[FileItem], manifest_rows: list[dict[str, str]]) -> str:
    top_dirs = Counter(top_dir(root, item.path) for item in files)
    ext_counts = Counter(extension(item.path) for item in files)
    ext_bytes: Counter[str] = Counter()
    for item in files:
        ext_bytes[extension(item.path)] += item.size

    manifest_ext_counts = Counter((row.get("extension") or "no-extension").strip().lower() for row in manifest_rows)
    manifest_month_counts = Counter((row.get("month") or "unknown").strip() for row in manifest_rows)
    status_counts = Counter((row.get("copy_status") or "unknown").strip() for row in manifest_rows)
    category_counts = Counter((row.get("category") or "unknown").strip() for row in manifest_rows)
    topic_counts, topic_examples = classify_manifest(manifest_rows, TOPIC_PATTERNS)
    sensitive_counts, sensitive_examples = classify_manifest(manifest_rows, SENSITIVE_PATTERNS)
    duplicate_names = duplicate_filename_groups(manifest_rows)

    total_bytes = sum(item.size for item in files)
    manifest_bytes = sum(parse_int(row.get("size_bytes")) for row in manifest_rows)
    backup_db_files = [item for item in files if item.path.name in BACKUP_FILENAMES]
    backup_bak_files = [item for item in files if item.path.name.startswith("BAK_")]
    largest_files = sorted(files, key=lambda item: item.size, reverse=True)[:20]
    largest_manifest = sorted(manifest_rows, key=lambda row: parse_int(row.get("size_bytes")), reverse=True)[:20]
    years: Counter[str] = Counter()
    for month, count in manifest_month_counts.items():
        if re.fullmatch(r"\d{4}-\d{2}", month):
            years[month[:4]] += count

    lines = [
        "# 微信归档文件全量分析",
        "",
        "## 口径",
        "",
        f"- 归档根目录：`{root}`",
        f"- 主清单：`{manifest}`",
        "- 本报告只做文件元数据分析：文件名、路径、扩展名、大小、修改时间、清单状态。",
        "- 没有读取文件正文，没有解析微信私有数据库，也没有打开 `Backup.db` / `BAK_*` 备份内容。",
        "",
        "## 总览",
        "",
        f"- 目录实际文件数：{len(files):,}",
        f"- 目录实际体量：{format_bytes(total_bytes)}",
        f"- manifest 文件记录：{len(manifest_rows):,}",
        f"- manifest 记录体量：{format_bytes(manifest_bytes)}",
        f"- 旧备份数据库相关文件：{len(backup_db_files):,}",
        f"- 旧备份 BAK 分片文件：{len(backup_bak_files):,}",
        "",
        "## 顶层目录分布",
        "",
        table(["目录", "文件数"], [(name, f"{count:,}") for name, count in top_dirs.most_common()]),
        "",
        "## 文件类型分布（实际目录）",
        "",
        table(
            ["扩展名", "文件数", "体量"],
            [(name, f"{count:,}", format_bytes(ext_bytes[name])) for name, count in ext_counts.most_common(30)],
        ),
        "",
        "## manifest 类型分布",
        "",
        table(["扩展名", "记录数"], [(name, f"{count:,}") for name, count in manifest_ext_counts.most_common(30)]),
        "",
        "## manifest 类别和复制状态",
        "",
        "### 类别",
        "",
        table(["类别", "记录数"], [(name, f"{count:,}") for name, count in category_counts.most_common()]),
        "",
        "### 复制状态",
        "",
        table(["状态", "记录数"], [(name, f"{count:,}") for name, count in status_counts.most_common()]),
        "",
        "## 时间分布",
        "",
        "### 年度",
        "",
        table(["年份", "记录数"], [(name, f"{count:,}") for name, count in sorted(years.items(), reverse=True)]),
        "",
        "### 最近月份 Top 24",
        "",
        table(["月份", "记录数"], [(name, f"{count:,}") for name, count in sorted(manifest_month_counts.items(), reverse=True)[:24]]),
        "",
        "## 主题聚类（按文件名关键词）",
        "",
        table(["主题", "命中记录数", "示例"], topic_rows(topic_counts, topic_examples)),
        "",
        "## 敏感文件名命中",
        "",
        table(["敏感类别", "命中记录数", "示例"], topic_rows(sensitive_counts, sensitive_examples)),
        "",
        "## 重复文件名",
        "",
        table(["文件名", "出现次数", "示例路径"], duplicate_names[:30]),
        "",
        "## 最大文件 Top 20（实际目录）",
        "",
        table(["大小", "路径"], [(format_bytes(item.size), f"`{item.path}`") for item in largest_files]),
        "",
        "## 最大文件 Top 20（manifest）",
        "",
        table(
            ["大小", "文件名", "归档路径"],
            [
                (
                    format_bytes(parse_int(row.get("size_bytes"))),
                    row.get("filename", ""),
                    f"`{row.get('archive_path', '')}`",
                )
                for row in largest_manifest
            ],
        ),
        "",
        "## 内容级分析建议",
        "",
        "- 第一优先：仅对低敏感的 PDF/PPTX/DOCX/XLSX/TXT/MD 做正文提取和摘要。",
        "- 第二优先：按主题先做项目簿，例如新能源物流、农牧食品、AI/智能体、医疗健康、投资/BP。",
        "- 不建议默认解析旧备份里的 `Backup.db` 或 `BAK_*`，除非你明确要求并接受隐私风险。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_index(path: Path, *, root: Path, files: list[FileItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["path", "relative_path", "extension", "size_bytes", "size_human", "modified"])
        for item in sorted(files, key=lambda file: str(file.path)):
            writer.writerow(
                [
                    str(item.path),
                    str(item.path.relative_to(root)) if item.path.is_relative_to(root) else str(item.path),
                    extension(item.path),
                    item.size,
                    format_bytes(item.size),
                    item.modified.isoformat(timespec="seconds") if item.modified else "",
                ]
            )


def classify_manifest(rows: list[dict[str, str]], patterns: dict[str, tuple[str, ...]]):
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        filename = row.get("filename", "")
        haystack = filename.casefold()
        for label, keywords in patterns.items():
            if any(keyword_matches(haystack, keyword) for keyword in keywords):
                counts[label] += 1
                if len(examples[label]) < 3:
                    examples[label].append(filename)
    return counts, examples


def topic_rows(counts: Counter[str], examples: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    return [
        (name, f"{count:,}", "；".join(examples.get(name, [])))
        for name, count in counts.most_common()
    ]


def duplicate_filename_groups(rows: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        filename = row.get("filename", "").strip()
        if not filename:
            continue
        groups[filename].append(row.get("archive_path", ""))
    result = [
        (filename, f"{len(paths):,}", f"`{paths[0]}`")
        for filename, paths in groups.items()
        if len(paths) > 1
    ]
    result.sort(key=lambda item: (-int(item[1].replace(",", "")), item[0]))
    return result


def keyword_matches(haystack_casefolded: str, keyword: str) -> bool:
    if keyword.isascii() and re.fullmatch(r"[A-Za-z0-9]+", keyword):
        pattern = rf"(?<![a-z0-9]){re.escape(keyword.casefold())}(?![a-z0-9])"
        return re.search(pattern, haystack_casefolded) is not None
    return keyword.casefold() in haystack_casefolded


def top_dir(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return "."
    return relative.parts[0] if relative.parts else "."


def extension(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix:
        return suffix
    return "no-extension"


def parse_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def table(headers: list[str], rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return "暂无。"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(sanitize_cell(str(cell)) for cell in row) + " |")
    return "\n".join(lines)


def sanitize_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
