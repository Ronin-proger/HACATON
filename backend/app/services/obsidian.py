"""Общий слой заметок: Local REST API Obsidian + запасное хранилище HACAOBS."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from ..config import settings

WIKI = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TAG = re.compile(r"(?<!\w)#([A-Za-zА-Яа-я0-9_/-]+)")
FM = re.compile(r"^---\n(.*?)\n---\n?", re.S)


def vault_root() -> Path:
    root = Path(settings.obsidian_vault_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.obsidian_api_key}",
        "Accept": "application/vnd.olrapi.note+json, application/json, text/markdown",
    }


def api_status() -> dict:
    urls = [settings.obsidian_api_url.rstrip("/")]
    if "27124" in urls[0]:
        urls.append(urls[0].replace("https://", "http://").replace("27124", "27123"))
    for base in urls:
        try:
            r = httpx.get(base + "/", headers=_headers(), timeout=1.6, verify=False)
            if r.status_code < 500:
                return {"ok": r.status_code < 400, "base": base, "status": r.status_code, "body": _safe_json(r)}
        except Exception as exc:
            last = str(exc)
            continue
    return {"ok": False, "base": None, "status": 0, "error": locals().get("last", "offline")}


def _safe_json(r: httpx.Response):
    try:
        return r.json()
    except Exception:
        return r.text[:240]


def _api_put(path: str, content: str) -> bool:
    st = api_status()
    if not st.get("ok") or not st.get("base"):
        return False
    url = f"{st['base']}/vault/{quote(path)}"
    try:
        r = httpx.put(
            url,
            headers={**_headers(), "Content-Type": "text/markdown"},
            content=content.encode("utf-8"),
            timeout=4,
            verify=False,
        )
        return r.status_code < 400
    except Exception:
        return False


def _rel(path: Path) -> str:
    return path.relative_to(vault_root()).as_posix()


def _safe_rel(path: str) -> str:
    clean = path.replace("\\", "/").lstrip("/")
    if ".." in Path(clean).parts:
        raise ValueError("bad path")
    return clean


def parse_note(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = text
    m = FM.match(text)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    tags = []
    raw_tags = meta.get("tags", "")
    if raw_tags.startswith("["):
        tags = [t.strip(" #[]'\"") for t in raw_tags.split(",") if t.strip(" #[]'\"")]
    elif raw_tags:
        tags = [t.strip(" #") for t in raw_tags.replace(",", " ").split() if t.strip(" #")]
    tags += TAG.findall(body)
    links = [w.strip() for w in WIKI.findall(body + "\n" + text[:200])]
    title = meta.get("title") or path.stem
    first = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), title)
    return {
        "path": _rel(path),
        "title": title or first,
        "folder": path.parent.relative_to(vault_root()).as_posix() if path.parent != vault_root() else "",
        "tags": sorted(set(tags)),
        "links": links,
        "author": meta.get("author") or meta.get("created_by") or "system",
        "type": meta.get("type") or (path.parent.name.lower() if path.parent != vault_root() else "note"),
        "created": meta.get("created") or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat(),
        "source": meta.get("source") or "vault",
        "chars": len(body),
        "preview": body.strip()[:280],
        "content": text,
    }


def list_notes() -> list[dict]:
    notes = []
    root = vault_root()
    for p in root.rglob("*.md"):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        try:
            notes.append(parse_note(p))
        except Exception:
            continue
    notes.sort(key=lambda n: (n["folder"], n["title"]))
    return notes


def get_note(path: str) -> dict:
    p = vault_root() / _safe_rel(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    return parse_note(p)


def write_note(path: str, content: str, *, sync_api: bool = True) -> dict:
    rel = _safe_rel(path)
    if not rel.endswith(".md"):
        rel += ".md"
    dest = vault_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
    if sync_api:
        _api_put(rel, content)
    return parse_note(dest)


def build_graph(notes: list[dict] | None = None) -> dict:
    notes = notes if notes is not None else list_notes()
    by_stem = {n["title"]: n["path"] for n in notes}
    by_stem.update({Path(n["path"]).stem: n["path"] for n in notes})
    nodes = []
    for n in notes:
        nodes.append({k: n[k] for k in (
            "path", "title", "folder", "tags", "author", "type", "created", "source", "chars", "preview", "links"
        )})
    edges = []
    seen = set()
    for n in notes:
        for raw in n["links"]:
            target = by_stem.get(raw) or by_stem.get(Path(raw).stem)
            if not target or target == n["path"]:
                continue
            key = tuple(sorted((n["path"], target)))
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": n["path"], "target": target})
    return {"nodes": nodes, "edges": edges}


def analytics(notes: list[dict] | None = None) -> dict:
    notes = notes if notes is not None else list_notes()
    folders, tags, authors, types, days = Counter(), Counter(), Counter(), Counter(), Counter()
    links = 0
    for n in notes:
        folders[n["folder"] or "root"] += 1
        authors[n["author"] or "—"] += 1
        types[n["type"] or "note"] += 1
        days[n["created"][:10]] += 1
        links += len(n["links"])
        for t in n["tags"]:
            tags[t] += 1
    return {
        "totals": {
            "notes": len(notes),
            "links": links,
            "tags": len(tags),
            "authors": len(authors),
            "folders": len(folders),
        },
        "by_folder": folders.most_common(),
        "by_tag": tags.most_common(12),
        "by_author": authors.most_common(),
        "by_type": types.most_common(),
        "by_day": sorted(days.items()),
    }


def compose_user_note(title: str, body: str, author: str, folder: str = "Inbox") -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^\wА-Яа-я-]+", "-", title.strip())[:60].strip("-") or "zametka"
    path = f"{folder}/{stamp} {slug}.md"
    content = (
        f"---\n"
        f"title: {title.strip()}\n"
        f"type: field\n"
        f"tags: [field, shared]\n"
        f"author: {author.strip() or 'crew'}\n"
        f"created: {stamp}\n"
        f"source: platform\n"
        f"---\n\n"
        f"# {title.strip()}\n\n"
        f"{body.strip()}\n\n"
        f"— [[{author.strip() or 'crew'}]] · [[{stamp}]] · см. [[SITE-01]]\n"
    )
    return path, content


def compose_ai_doc(context: dict | None = None) -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    day = datetime.now().strftime("%Y-%m-%d")
    ctx = context or {}
    title = "AI · журнал площадки"
    path = f"AI/{day} журнал.md"
    units = ctx.get("units") or ["CRN-A-MSK", "BLD-A-MSK", "BLD-B-MSK", "BLD-C-MSK", "PIT-01-MSK"]
    content = (
        f"---\n"
        f"title: {title}\n"
        f"type: ai-doc\n"
        f"tags: [ai, documentation, site-01]\n"
        f"author: stroysync-ai\n"
        f"created: {day}\n"
        f"source: ai\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"Черновик вшитого ИИ. Позже модель будет править этот файл по кадрам и WBS.\n\n"
        f"## Сводка {stamp}\n\n"
        f"- Площадка: [[SITE-01]]\n"
        f"- Каркас: [[Корпус A]], [[Корпус B]], фундамент [[Корпус C]]\n"
        f"- Земляные: [[Котлован]]\n"
        f"- Подъём: [[Башенный кран 1]], [[Башенный кран 2]]\n"
        f"- Люди: [[Смена]]\n"
        f"- Охрана труда: [[Техника безопасности]]\n\n"
        f"## Юниты в контуре\n\n"
        + "".join(f"- `{u}`\n" for u in units)
        + "\n## Риски\n\n"
        f"- Корпус C отстаёт от графика — см. [[Корпус C]] и [[WBS]].\n"
        f"- Сигнал крана №2 умеренный, ветер.\n"
        f"- Склад материалов: нехватка плёнки — [[Склад материалов]].\n\n"
        f"## Следующие действия ИИ\n\n"
        f"1. Сверить технику с [[WBS]].\n"
        f"2. Дописать акт скрытых работ по [[Котлован]].\n"
        f"3. Обновить [[Журнал работ]].\n"
    )
    return path, content


SEED: dict[str, str] = {
    "SITE-01.md": """---
title: SITE-01
type: moc
tags: [index, site-01]
author: system
created: 2026-09-24
source: seed
---

# SITE-01 · цифровой двойник

Карта знаний площадки. Все смены пишут сюда — заметки общие.

## Объекты

- [[Корпус A]] — монолит, 5 этажей
- [[Корпус B]] — высотка, 7 этажей
- [[Корпус C]] — ростверк, отставание
- [[Котлован]] — шпунт и водоотлив
- [[Башенный кран 1]] · [[Башенный кран 2]]
- [[Бытовой городок]] · [[КПП]]
- [[Склад материалов]] · [[Растворный узел]]

## Контур

- [[WBS]] · [[Журнал работ]] · [[Смена]]
- [[Техника безопасности]]
- [[AI · журнал площадки]]
""",
    "Site/Корпус A.md": """---
title: Корпус A
type: building
tags: [building, wbs-4, concrete]
author: system
created: 2026-09-24
source: seed
---

# Корпус A

Монолитный каркас, 5 этажей. Леса по южному фасаду. Обслуживает [[Башенный кран 1]].

- Плиты ~60%
- Сетка и ограждение кровли
- WBS 4.2 / 4.3 — см. [[WBS]]

Связано: [[SITE-01]], [[Корпус B]], [[Смена]].
""",
    "Site/Корпус B.md": """---
title: Корпус B
type: building
tags: [building, wbs-5, facade]
author: system
created: 2026-09-24
source: seed
---

# Корпус B

Секция 2, 7 этажей. Кирпич + минвата. Подача с [[Башенный кран 2]].

- Лестничная клетка до +6
- Леса на южном торце
- WBS 5.1

Связано: [[SITE-01]], [[Корпус A]], [[Техника безопасности]].
""",
    "Site/Корпус C.md": """---
title: Корпус C
type: building
tags: [building, foundation, warning]
author: system
created: 2026-09-24
source: seed
---

# Корпус C

Фундамент / ростверк, 2 этажа. Отставание от [[WBS]].

- Армокаркасы на пятне
- Ожидание бетона ночью
- Риск: срыв окна бетонирования

Связано: [[Котлован]], [[Растворный узел]], [[Журнал работ]].
""",
    "Site/Котлован.md": """---
title: Котлован
type: pit
tags: [earthworks, water, safety]
author: system
created: 2026-09-24
source: seed
---

# Котлован

Отм. −2.7 м. Шпунт, распорки, водоотлив.

Техника: два экскаватора, бульдозер. См. [[Экскаваторы]].

Связано: [[Корпус C]], [[SITE-01]], [[Техника безопасности]].
""",
    "Equipment/Башенный кран 1.md": """---
title: Башенный кран 1
type: equipment
tags: [crane, lift, crn-a]
author: system
created: 2026-09-24
source: seed
---

# Башенный кран 1

Liebherr 280 EC-H, стрела 62 м. Юнит `CRN-A-MSK`.

- Груз на крюке 8.2 т
- Обслуживает [[Корпус A]]
- Сессия с 06:20

Связано: [[Башенный кран 2]], [[Смена]], [[Техника безопасности]].
""",
    "Equipment/Башенный кран 2.md": """---
title: Башенный кран 2
type: equipment
tags: [crane, lift, crn-b]
author: system
created: 2026-09-24
source: seed
---

# Башенный кран 2

Potain MDT 319, стрела 55 м. Юнит `CRN-B-MSK`.

- Контргруз 18 т
- Ветер 7 м/с — режим снижен
- Обслуживает [[Корпус B]]
""",
    "Equipment/Экскаваторы.md": """---
title: Экскаваторы
type: equipment
tags: [excavator, earthworks]
author: system
created: 2026-09-24
source: seed
---

# Экскаваторы

`EXC-01` и `EXC-02` в [[Котлован]]. `EXC-03` на западном откосе.

Связано: [[SITE-01]], [[Журнал работ]].
""",
    "Site/Бытовой городок.md": """---
title: Бытовой городок
type: welfare
tags: [people, camp]
author: system
created: 2026-09-24
source: seed
---

# Бытовой городок

Офис / столовая / штаб. 46 человек на смене — [[Смена]].

Связано: [[КПП]], [[SITE-01]].
""",
    "Site/КПП.md": """---
title: КПП
type: gate
tags: [logistics, anpr]
author: system
created: 2026-09-24
source: seed
---

# КПП / въезд

Два створа, мойка колёс, ANPR. Очередь: 1 миксер.

Связано: [[Растворный узел]], [[Смена]].
""",
    "Site/Склад материалов.md": """---
title: Склад материалов
type: stock
tags: [logistics, materials, warning]
author: system
created: 2026-09-24
source: seed
---

# Склад материалов

Арматура, трубы, мешки, кирпич, плёнка / рубероид.

Нехватка укрывной плёнки на [[Корпус C]].

Связано: [[Растворный узел]], [[SITE-01]].
""",
    "Site/Растворный узел.md": """---
title: Растворный узел
type: plant
tags: [concrete, plant]
author: system
created: 2026-09-24
source: seed
---

# Растворный узел

Силос, бункер, ДГУ. Подача на [[Корпус A]] и [[Корпус B]]. Запас цемента 18 т.
""",
    "Schedule/WBS.md": """---
title: WBS
type: schedule
tags: [wbs, plan]
author: system
created: 2026-09-24
source: seed
---

# WBS

- 3.1 ростверк — [[Корпус C]]
- 4.2 / 4.3 каркас — [[Корпус A]]
- 5.1 фасад — [[Корпус B]]
- земляные — [[Котлован]]

Связано: [[Журнал работ]], [[SITE-01]].
""",
    "Journal/Журнал работ.md": """---
title: Журнал работ
type: journal
tags: [journal, daily]
author: прораб
created: 2026-09-24
source: seed
---

# Журнал работ

24.09 — ночная заливка перенесена. Ждём миксер на [[КПП]].

Кран №2 в сниженном режиме. Смена 46 чел. — [[Смена]].

Связано: [[WBS]], [[AI · журнал площадки]].
""",
    "People/Смена.md": """---
title: Смена
type: people
tags: [people, crew]
author: табельный
created: 2026-09-24
source: seed
---

# Смена

46 человек. Штаб в [[Бытовой городок]]. Допуск на леса корпуса A.

Связано: [[Техника безопасности]], [[SITE-01]].
""",
    "Safety/Техника безопасности.md": """---
title: Техника безопасности
type: safety
tags: [safety, ppe]
author: от
created: 2026-09-24
source: seed
---

# Техника безопасности

Каски, жилеты, стропы на [[Башенный кран 1]] и [[Башенный кран 2]].

Запрет на край шпунта без страховки — [[Котлован]].
""",
    "AI/AI · журнал площадки.md": """---
title: AI · журнал площадки
type: ai-doc
tags: [ai, documentation]
author: stroysync-ai
created: 2026-09-24
source: ai
---

# AI · журнал площадки

Стартовый черновик вшитого ИИ. Новые сводки пишутся кнопкой «ИИ: журнал» и правятся моделью позже.

Контур: [[SITE-01]], [[WBS]], [[Журнал работ]].
""",
    "Inbox/Правила заметок.md": """---
title: Правила заметок
type: field
tags: [shared, inbox]
author: system
created: 2026-09-24
source: seed
---

# Правила заметок

Пишите коротко. Ставьте `[[ссылки]]` на объекты. Заметка видна всей площадке.

Связано: [[SITE-01]], [[Смена]].
""",
}


def ensure_seed() -> dict:
    written = []
    for rel, text in SEED.items():
        dest = vault_root() / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_text(text, encoding="utf-8")
            written.append(rel)
            _api_put(rel, text)
    welcome = vault_root() / "Добро пожаловать.md"
    if welcome.exists() and "ваше новое" in welcome.read_text(encoding="utf-8"):
        # keep as-is; already in vault
        pass
    return {"seeded": written, "total": len(list_notes()), "api": api_status()}
