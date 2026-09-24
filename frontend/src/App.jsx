import { useEffect, useState } from "react";
import { api } from "./api";

const TABS = [
  ["live", "Мониторинг"],
  ["schedule", "График"],
  ["cameras", "Камеры"],
  ["history", "История"],
];

const STATUS_RU = {
  on_track: "в графике",
  warning: "отклонение",
  critical: "критично",
  unknown: "нет данных",
  active: "идёт",
  past: "завершён",
  future: "план",
};

const EQUIP_RU = {
  dump_truck: "Самосвал",
  excavator: "Экскаватор",
  roller: "Каток",
  manipulator_crane: "Кран-манипулятор",
  concrete_mixer: "Бетоносмеситель",
  bulldozer: "Бульдозер",
  truck: "Грузовик",
  mobile_crane: "Автокран",
};

export default function App() {
  const [tab, setTab] = useState("live");
  const [schedule, setSchedule] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [samples, setSamples] = useState([]);
  const [guide, setGuide] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [cameraId, setCameraId] = useState("CAM-01");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);

  const load = async () => {
    const [sch, cam, smp, dash, hist, g] = await Promise.all([
      api.schedule(),
      api.cameras(),
      api.samples(),
      api.dashboard(),
      api.snapshots(),
      api.cameraGuide(),
    ]);
    setSchedule(sch);
    setCameras(cam);
    setSamples(smp);
    setDashboard(dash);
    setHistory(hist);
    setGuide(g);
  };

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, []);

  const runSample = async (id) => {
    setBusy(true);
    setError("");
    try {
      const data = await api.runSample(id);
      setResult(data.snapshot);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const onUpload = async (file) => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const data = await api.analyze({ file, cameraId });
      setResult(data.snapshot);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const counts = dashboard?.status_counts || {};
  const snap = result || dashboard?.recent?.[0];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">SS</div>
          <div>
            <h1>StroySync</h1>
            <p>зрение площадки ↔ календарный график</p>
          </div>
        </div>
        <nav className="nav">
          {TABS.map(([id, label]) => (
            <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "live" && (
        <div>
          <div style={{ padding: "16px 16px 0" }}>
            <div className="kpis">
              <div className="kpi"><span>В графике</span><b>{counts.on_track || 0}</b></div>
              <div className="kpi"><span>Отклонения</span><b>{counts.warning || 0}</b></div>
              <div className="kpi"><span>Критических</span><b>{counts.critical || 0}</b></div>
              <div className="kpi"><span>Снимков</span><b>{history.length}</b></div>
            </div>
          </div>
          <div className="layout">
            <aside className="panel">
              <h2>Камера и сценарии</h2>
              {cameras.map((c) => (
                <button key={c.id} className={`cam ${cameraId === c.id ? "active" : ""}`} onClick={() => setCameraId(c.id)}>
                  <b>{c.id}</b> · {c.name}
                  <div className="muted">{c.zone} · WBS {c.linked_wbs.join(", ")}</div>
                </button>
              ))}
              <div className="drop">
                <div className="muted">Загрузите снимок площадки</div>
                <input
                  type="file"
                  accept="image/*"
                  style={{ marginTop: 10, color: "#8b98ab" }}
                  onChange={(e) => onUpload(e.target.files?.[0])}
                />
              </div>
              <h3>Демо-сцены</h3>
              {samples.map((s) => (
                <button key={s.id} className="sample" disabled={busy} onClick={() => runSample(s.id)}>
                  <b>{s.title}</b>
                  <div className="muted">{s.camera_id} · {s.note}</div>
                </button>
              ))}
              {error && <p className="muted" style={{ color: "var(--crit)" }}>{error}</p>}
            </aside>

            <section className="panel">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                <h2>Снимок и распознавание</h2>
                {snap && <span className={`badge ${snap.site_status}`}>{STATUS_RU[snap.site_status] || snap.site_status}</span>}
              </div>
              <div className="viewport">
                {snap?.annotated_url || snap?.original_url ? (
                  <img src={snap.annotated_url || snap.original_url} alt="Снимок площадки" />
                ) : (
                  <p className="muted" style={{ padding: 24 }}>Выберите демо-сцену или загрузите фото.</p>
                )}
              </div>
              {snap && (
                <>
                  <p className="muted" style={{ marginTop: 10 }}>{snap.summary}</p>
                  <div className="chips">
                    {Object.entries(snap.detected_counts || {}).map(([code, n]) => (
                      <span className="chip" key={code}>{EQUIP_RU[code] || code}: {n}</span>
                    ))}
                    <span className="chip">модель: {snap.detector_backend}</span>
                    <span className="chip">score {Number(snap.match_score || 0).toFixed(2)}</span>
                  </div>
                </>
              )}
            </section>

            <aside className="panel">
              <h2>Сопоставление с графиком</h2>
              {(snap?.active_stages || []).length === 0 && <p className="muted">Нет активного этапа для этой камеры на дату снимка.</p>}
              {(snap?.active_stages || []).map((s) => (
                <div className="stage" key={s.wbs}>
                  <div className="wbs">{s.wbs}</div>
                  <b>{s.name}</b>
                  <div className="muted">{s.start_date} — {s.end_date} · сходство {s.score}</div>
                </div>
              ))}
              <h3 style={{ marginTop: 16 }}>Предупреждения</h3>
              {(snap?.deviations || []).map((d, i) => (
                <div className={`alert ${d.severity}`} key={i}>
                  <h4>
                    <span className={`badge ${d.severity}`}>{d.severity}</span> {d.title}
                  </h4>
                  <p>{d.explanation}</p>
                </div>
              ))}
            </aside>
          </div>
        </div>
      )}

      {tab === "schedule" && <SchedulePage schedule={schedule} />}
      {tab === "cameras" && <CamerasPage cameras={cameras} guide={guide} />}
      {tab === "history" && <HistoryPage history={history} onOpen={setResult} goLive={() => setTab("live")} />}
    </div>
  );
}

function SchedulePage({ schedule }) {
  return (
    <div className="page">
      <div className="panel">
        <h2>Календарный график и допустимая техника</h2>
        <p className="muted">Связь «этап → техника» задана явно: обязательный, допустимый и запрещённый состав. Снимок сравнивается с активным WBS зоны камеры.</p>
        <table className="table">
          <thead>
            <tr>
              <th>WBS</th><th>Этап</th><th>Зона</th><th>Сроки</th><th>Статус</th><th>Обязательно</th><th>Запрещено</th>
            </tr>
          </thead>
          <tbody>
            {schedule.map((s) => (
              <tr key={s.wbs}>
                <td className="wbs">{s.wbs}</td>
                <td style={{ paddingLeft: 8 + s.level * 8 }}>{s.name}</td>
                <td>{s.zone}</td>
                <td>{s.start_date} — {s.end_date}</td>
                <td><span className={`badge ${s.time_status}`}>{STATUS_RU[s.time_status]}</span></td>
                <td>{(s.required_equipment || []).map((c) => EQUIP_RU[c] || c).join(", ")}</td>
                <td>{(s.forbidden_equipment || []).map((c) => EQUIP_RU[c] || c).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CamerasPage({ cameras, guide }) {
  return (
    <div className="page">
      <div className="grid-2">
        <div className="panel">
          <h2>Камеры и привязка к этапам</h2>
          {cameras.map((c) => (
            <div className="stage" key={c.id}>
              <b>{c.id} — {c.name}</b>
              <div className="muted">{c.view}</div>
              <div className="chips">
                <span className="chip">{c.zone}</span>
                <span className="chip">{c.height_m} м / {c.angle_deg}°</span>
                {(c.linked_wbs || []).map((w) => <span className="chip" key={w}>{w}</span>)}
              </div>
              <p className="muted">{c.recommendations}</p>
            </div>
          ))}
        </div>
        <div className="panel">
          <h2>Рекомендации по установке</h2>
          {(guide?.principles || []).map((p) => (
            <div className="stage" key={p.title}>
              <b>{p.title}</b>
              <p className="muted">{p.text}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function HistoryPage({ history, onOpen, goLive }) {
  return (
    <div className="page">
      <div className="panel">
        <h2>История анализов</h2>
        <table className="table">
          <thead>
            <tr><th>ID</th><th>Камера</th><th>Время</th><th>Статус</th><th>Техника</th><th></th></tr>
          </thead>
          <tbody>
            {history.map((s) => (
              <tr key={s.id}>
                <td>{s.id}</td>
                <td>{s.camera_id}</td>
                <td>{s.captured_at.replace("T", " ").slice(0, 19)}</td>
                <td><span className={`badge ${s.site_status}`}>{STATUS_RU[s.site_status]}</span></td>
                <td>{Object.entries(s.detected_counts || {}).map(([c, n]) => `${EQUIP_RU[c] || c}×${n}`).join(", ")}</td>
                <td>
                  <button className="primary" onClick={() => { onOpen(s); goLive(); }}>открыть</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
