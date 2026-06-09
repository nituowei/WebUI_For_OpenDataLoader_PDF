const state = {
  config: null,
  jobId: null,
  pollTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

function selectedFormats() {
  return $$('input[name="format"]:checked').map((input) => input.value);
}

function applyConfig(config) {
  state.config = config;
  const inputPaths = config.input_paths || [];
  $("#inputDir").value = inputPaths.length > 0
    ? `${inputPaths.length} 个 PDF：${inputPaths.map((path) => path.split("/").filter(Boolean).pop()).join(", ")}`
    : config.input_dir || "";
  $("#outputDir").value = config.output_dir || "";
  $("#imageOutput").value = config.image_output || "off";
  $("#useHybrid").checked = Boolean(config.use_hybrid_when_running);
  $$('input[name="format"]').forEach((input) => {
    input.checked = (config.formats || []).includes(input.value);
  });
}

function applyStatus(payload) {
  applyConfig(payload.config);
  $("#pythonStatus").textContent = payload.deps.python;
  $("#javaStatus").textContent = payload.deps.java_ok ? "Ready" : "Missing";
  $("#odlStatus").textContent = payload.deps.opendataloader_ok ? "Ready" : "Missing";

  const badge = $("#daemonBadge");
  badge.classList.toggle("running", payload.daemon.running);
  badge.textContent = payload.daemon.running
    ? `Daemon: running #${payload.daemon.pid}`
    : "Daemon: stopped";
}

async function refreshStatus() {
  const payload = await api("/api/status");
  applyStatus(payload);
}

async function saveConfig() {
  const formats = selectedFormats();
  if (formats.length === 0) {
    throw new Error("至少选择一种输出格式。");
  }
  const payload = {
    ...state.config,
    formats,
    image_output: $("#imageOutput").value,
    use_hybrid_when_running: $("#useHybrid").checked,
  };
  const result = await api("/api/config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  applyConfig(result.config);
}

async function pickFolder(purpose) {
  $("#logOutput").textContent = "等待 macOS 选择器...";
  if (purpose === "input") {
    const result = await api("/api/pick-pdfs", {
      method: "POST",
      body: "{}",
    });
    applyConfig(result.config);
    $("#logOutput").textContent = `已选择 ${result.paths.length} 个 PDF：\n${result.paths.join("\n")}`;
    return;
  }
  const result = await api("/api/pick-folder", {
    method: "POST",
    body: JSON.stringify({ purpose }),
  });
  applyConfig(result.config);
  $("#logOutput").textContent = `已选择：${result.path}`;
}

async function startDaemon() {
  await api("/api/daemon/start", { method: "POST", body: "{}" });
  await refreshStatus();
}

async function stopDaemon() {
  await api("/api/daemon/stop", { method: "POST", body: "{}" });
  await refreshStatus();
}

async function shutdownWebui() {
  await api("/api/shutdown", { method: "POST", body: "{}" });
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  $("#jobState").textContent = "WebUI 已关闭";
  $("#logOutput").textContent = "8787 主进程正在关闭。需要再次使用时，运行 ./start-webui.sh。";
}

async function startConvert() {
  await saveConfig();
  const result = await api("/api/convert", { method: "POST", body: "{}" });
  state.jobId = result.job_id;
  $("#jobState").textContent = `任务 ${state.jobId} 已提交`;
  $("#logOutput").textContent = "任务排队中...";
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  state.pollTimer = setInterval(pollJob, 1200);
  await pollJob();
}

async function pollJob() {
  if (!state.jobId) return;
  const result = await api(`/api/job?id=${encodeURIComponent(state.jobId)}`);
  const job = result.job;
  $("#jobState").textContent = `任务 ${job.id}: ${job.status}`;
  $("#logOutput").textContent = job.error || job.log || "运行中...";
  if (job.status === "done" || job.status === "failed") {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
    await refreshStatus();
  }
}

function bindEvents() {
  $("#pickInput").addEventListener("click", () => pickFolder("input").catch(showError));
  $("#pickOutput").addEventListener("click", () => pickFolder("output").catch(showError));
  $("#startDaemon").addEventListener("click", () => startDaemon().catch(showError));
  $("#stopDaemon").addEventListener("click", () => stopDaemon().catch(showError));
  $("#convert").addEventListener("click", () => startConvert().catch(showError));
  $("#shutdownWebui").addEventListener("click", () => shutdownWebui().catch(showError));
  $$('input[name="format"], #useHybrid, #imageOutput').forEach((input) => {
    input.addEventListener("change", () => saveConfig().catch(showError));
  });
}

function showError(error) {
  $("#jobState").textContent = "出错";
  $("#logOutput").textContent = error.message;
}

bindEvents();
refreshStatus().catch(showError);
