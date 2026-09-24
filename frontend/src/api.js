const json = async (res) => {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
};

export const api = {
  health: () => fetch("/api/health").then(json),
  equipment: () => fetch("/api/equipment").then(json),
  schedule: () => fetch("/api/schedule").then(json),
  cameras: () => fetch("/api/cameras").then(json),
  dashboard: () => fetch("/api/dashboard").then(json),
  samples: () => fetch("/api/demo/samples").then(json),
  cameraGuide: () => fetch("/api/camera-guide").then(json),
  snapshots: () => fetch("/api/snapshots").then(json),
  runSample: (id) =>
    fetch(`/api/demo/run/${id}`, { method: "POST" }).then(json),
  analyze: ({ file, cameraId, capturedAt }) => {
    const data = new FormData();
    data.append("file", file);
    data.append("camera_id", cameraId);
    if (capturedAt) data.append("captured_at", capturedAt);
    return fetch("/api/analyze", { method: "POST", body: data }).then(json);
  },
  twinCurrent: () => fetch("/api/twin/current").then(json),
  twinReset: () => fetch("/api/twin/reset", { method: "POST" }).then(json),
  twinFromHistory: () => fetch("/api/twin/from-history", { method: "POST" }).then(json),
  reconstruct: (files, cameraId) => {
    const data = new FormData();
    [...files].forEach((f) => data.append("files", f));
    data.append("camera_id", cameraId);
    return fetch("/api/twin/reconstruct", { method: "POST", body: data }).then(json);
  },
  criteria: () => fetch("/api/criteria").then(json),
};
