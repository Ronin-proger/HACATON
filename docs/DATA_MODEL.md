# Модель данных StroySync

```
equipment_types 1 ──< detections >── snapshots >── cameras
work_stages (WBS, иерархия)
cameras.linked_wbs ──► work_stages.wbs
snapshots 1 ──< deviations (правило, severity, evidence, wbs)
```

Статусы снимка: `on_track | warning | critical | unknown`.
Коды отклонений: `MISSING_REQUIRED`, `UNEXPECTED_EQUIPMENT`, `FORBIDDEN_EQUIPMENT`, `AHEAD_OF_SCHEDULE`, `BEHIND_SCHEDULE`, `NO_ACTIVITY`, `WORK_OUTSIDE_SCHEDULE`, `ON_TRACK`.
