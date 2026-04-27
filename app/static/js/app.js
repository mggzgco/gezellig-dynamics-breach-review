let selectedFiles = [];
let currentJobId = null;
let reportCollapsed = false;
let runHistory = [];
let currentBuildInfo = null;
let currentEventSource = null;
let statusPollIntervalId = null;
let streamConnectTimeoutId = null;
let streamHasDeliveredEvent = false;
let setupPollIntervalId = null;
let currentSetupStatus = null;
let startupWizardForced = false;
let activeModalDepth = 0;
let setupHeartbeatIntervalId = null;
let historyHeartbeatIntervalId = null;
let autoDeepCheckInFlight = false;
let setupConfirmed = false;

const appShell = document.getElementById("appShell");
const uploadZone = document.getElementById("uploadZone");
const uploadZoneTitle = document.getElementById("uploadZoneTitle");
const uploadZoneText = document.getElementById("uploadZoneText");
const uploadFeedback = document.getElementById("uploadFeedback");
const uploadFeedbackTitle = document.getElementById("uploadFeedbackTitle");
const uploadFeedbackText = document.getElementById("uploadFeedbackText");
const uploadFeedbackMeta = document.getElementById("uploadFeedbackMeta");
const fileInput = document.getElementById("fileInput");
const submitBtn = document.getElementById("submitBtn");
const fileList = document.getElementById("fileList");
const fileDetails = document.getElementById("fileDetails");
const fileItems = document.getElementById("fileItems");
const selectedSummary = document.getElementById("selectedSummary");
const progressPanel = document.getElementById("progressPanel");
const resultsPanel = document.getElementById("resultsPanel");
const reviewIntake = document.getElementById("reviewIntake");
const workspaceGate = document.getElementById("workspaceGate");
const errorPanel = document.getElementById("errorPanel");
const fileReviewBtn = document.getElementById("fileReviewBtn");
const runHistoryEmpty = document.getElementById("runHistoryEmpty");
const runHistoryList = document.getElementById("runHistoryList");
const startupWizard = document.getElementById("startupWizard");
const activityModal = document.getElementById("activityModal");

initializeSidebarState();
setView("landing");
setReviewMode("idle");
startSetupHeartbeat();
startHistoryHeartbeat();
refreshSetupStatus(true, { showModal: false, quiet: true });
refreshJobHistory();

uploadZone.addEventListener("dragover", (event) => {
    if (!setupConfirmed) {
        event.preventDefault();
        uploadZone.classList.remove("drag-over");
        return;
    }
    event.preventDefault();
    uploadZone.classList.add("drag-over");
});

uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("drag-over");
});

uploadZone.addEventListener("drop", (event) => {
    event.preventDefault();
    uploadZone.classList.remove("drag-over");
    if (!setupConfirmed) {
        openStartupWizard(true);
        return;
    }
    const droppedFiles = Array.from(event.dataTransfer.files || []);
    const files = droppedFiles.filter((file) => file.name.toLowerCase().endsWith(".eml"));
    if (files.length > 0) {
        selectedFiles = files;
        updateFileList();
        setView("review");
    } else if (droppedFiles.length > 0) {
        showError("Only `.eml` files can be uploaded. Remove unsupported files and retry the full batch.");
    }
});

uploadZone.addEventListener("click", () => {
    if (!setupConfirmed) {
        openStartupWizard(true);
        return;
    }
    fileInput.click();
});

fileInput.addEventListener("change", (event) => {
    if (!setupConfirmed) {
        fileInput.value = "";
        openStartupWizard(true);
        return;
    }
    selectedFiles = Array.from(event.target.files || []);
    updateFileList();
});

function initializeSidebarState() {
    if (window.localStorage.getItem("gd-review-sidebar") === "collapsed") {
        appShell.classList.add("sidebar-collapsed");
    }
}

function toggleSidebar() {
    appShell.classList.toggle("sidebar-collapsed");
    window.localStorage.setItem(
        "gd-review-sidebar",
        appShell.classList.contains("sidebar-collapsed") ? "collapsed" : "expanded",
    );
}

function setView(viewName) {
    document.getElementById("pageLanding").classList.toggle("active", viewName === "landing");
    document.getElementById("pageReview").classList.toggle("active", viewName === "review");
    document.getElementById("pageRuns").classList.toggle("active", viewName === "runs");
    document.getElementById("navLanding").classList.toggle("active", viewName === "landing");
    document.getElementById("navReview").classList.toggle("active", viewName === "review");
    document.getElementById("navRuns").classList.toggle("active", viewName === "runs");
    document.getElementById("pageHeading").textContent = viewName === "review"
        ? "Breach review workspace"
        : (viewName === "runs"
            ? "Saved review runs"
            : "Private review of leaked email evidence");
}

function setReviewMode(mode) {
    if (mode === "running") {
        reviewIntake.setAttribute("data-hidden", "true");
        progressPanel.classList.add("show");
        resultsPanel.classList.remove("show");
        return;
    }

    if (mode === "complete") {
        reviewIntake.setAttribute("data-hidden", "true");
        progressPanel.classList.remove("show");
        resultsPanel.classList.add("show");
        return;
    }

    reviewIntake.setAttribute("data-hidden", "false");
    progressPanel.classList.remove("show");
    resultsPanel.classList.remove("show");
}

async function refreshJobHistory() {
    try {
        const response = await fetch("/api/jobs");
        if (!response.ok) {
            throw new Error("Recent runs could not be loaded");
        }
        const payload = await response.json();
        runHistory = Array.isArray(payload.jobs) ? payload.jobs : [];
        renderRunHistory();
    } catch (error) {
        console.warn("Run history unavailable", error);
    }
}

function renderRunHistory() {
    runHistoryList.innerHTML = "";

    if (!runHistory.length) {
        runHistoryEmpty.classList.add("show");
        return;
    }

    runHistoryEmpty.classList.remove("show");
    runHistory.forEach((job) => {
        const item = document.createElement("article");
        item.className = `run-history-item${job.job_id === currentJobId ? " is-active" : ""}`;

        const summary = job.summary || null;
        const processed = Number(job.progress?.processed || 0);
        const total = Number(job.progress?.total || 0);
        const progressLabel = total > 0 ? `${processed}/${total}` : `${processed}`;
        const statusLabel = formatStatus(job.status || "queued");
        const title = summary?.total_files_processed
            ? `${summary.total_files_processed} files · ${summary.persons_found || 0} records`
            : (job.progress?.current_file || "Awaiting run details");
        const meta = [
            formatRunTimestamp(job),
            summary?.build_label ? `Build ${summary.build_label}` : "",
            job.error ? "Error recorded" : "",
        ].filter(Boolean).join(" · ");
        const stats = summary
            ? [
                `${summary.high_risk || 0} high risk`,
                `${summary.medium_risk || 0} medium risk`,
                `${summary.notification_required || 0} notify`,
            ].join(" · ")
            : (job.status === "processing"
                ? `${progressLabel} processed`
                : "No summary available yet");
        const buttonLabel = summary || job.result_available
            ? "Open result"
            : (job.status === "error" ? "Inspect run" : "Open run");
        const deleteButton = job.can_delete
            ? `<button class="btn-tertiary" type="button" data-job-delete="${escapeHtml(job.job_id)}">Delete</button>`
            : "";

        item.innerHTML = `
            <div class="run-history-top">
                <div class="run-history-copy">
                    <strong>${escapeHtml(statusLabel)}</strong>
                    <span>${escapeHtml(title)}</span>
                </div>
                <div class="toolbar-group">
                    <span class="status-pill ${statusTone(job.status)}"><span>●</span><span>${escapeHtml(statusLabel)}</span></span>
                    <button class="btn-secondary" type="button" data-job-open="${escapeHtml(job.job_id)}">${escapeHtml(buttonLabel)}</button>
                    ${deleteButton}
                </div>
            </div>
            <div class="run-history-bottom">
                <div class="run-history-meta">${escapeHtml(meta || "Run saved in local history")}</div>
                <div class="run-history-stats">${escapeHtml(stats)}</div>
            </div>
        `;

        const openButton = item.querySelector("[data-job-open]");
        if (openButton) {
            openButton.addEventListener("click", () => openRun(openButton.getAttribute("data-job-open")));
        }
        const deleteButtonElement = item.querySelector("[data-job-delete]");
        if (deleteButtonElement) {
            deleteButtonElement.addEventListener("click", () => deleteRun(deleteButtonElement.getAttribute("data-job-delete")));
        }

        runHistoryList.appendChild(item);
    });
}

function statusTone(status) {
    switch (status) {
        case "complete":
            return "ok";
        case "error":
            return "error";
        default:
            return "warn";
    }
}

function formatRunTimestamp(job) {
    const value = job.completed_at || job.created_at;
    if (!value) {
        return "Saved run";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return "Saved run";
    }

    return date.toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function upsertCurrentRunHistory(update) {
    if (!currentJobId) {
        return;
    }

    const existingIndex = runHistory.findIndex((job) => job.job_id === currentJobId);
    const base = existingIndex >= 0
        ? runHistory[existingIndex]
        : {
            job_id: currentJobId,
            status: "queued",
            created_at: new Date().toISOString(),
            completed_at: null,
            error: null,
            progress: {
                processed: 0,
                total: 0,
                current_file: "",
                persons_found: 0,
                message: "",
            },
            result_available: false,
            summary: null,
        };

    const next = {
        ...base,
        ...update,
        progress: {
            ...(base.progress || {}),
            ...(update.progress || {}),
        },
        summary: Object.prototype.hasOwnProperty.call(update, "summary")
            ? update.summary
            : base.summary,
    };

    if (existingIndex >= 0) {
        runHistory.splice(existingIndex, 1);
    }
    runHistory.unshift(next);
    renderRunHistory();
}

async function openRun(jobId) {
    if (!jobId) {
        return;
    }

    try {
        stopStatusStreaming();
        hideError();
        currentJobId = jobId;
        setView("review");

        const statusResponse = await fetch(`/api/jobs/${jobId}/status`);
        if (!statusResponse.ok) {
            throw new Error("Run status could not be loaded");
        }
        const statusPayload = await statusResponse.json();

        if (statusPayload.result_available || statusPayload.status === "complete") {
            const resultResponse = await fetch(`/api/jobs/${jobId}/result`);
            if (!resultResponse.ok) {
                throw new Error("Run result could not be loaded");
            }
            const summary = await resultResponse.json();
            await showResults(jobId, summary);
            return;
        }

        if (statusPayload.status === "error") {
            resetExperience();
            showError(`This run failed: ${statusPayload.error || "Unknown error"}`);
            return;
        }

        setReviewMode("running");
        applyProgressUpdate({
            status: statusPayload.status,
            processed: statusPayload.progress?.processed || 0,
            total: statusPayload.progress?.total || 0,
            current_file: statusPayload.progress?.current_file || "",
            persons_found: statusPayload.progress?.persons_found || 0,
            message: statusPayload.progress?.message || "Run resumed from saved history.",
        });
        streamProgress(jobId);
    } catch (error) {
        showError(`Could not reopen run: ${error.message}`);
    } finally {
        renderRunHistory();
    }
}

async function deleteRun(jobId) {
    if (!jobId) {
        return;
    }

    const job = runHistory.find((item) => item.job_id === jobId);
    const label = job?.summary?.total_files_processed
        ? `${job.summary.total_files_processed} file run`
        : (job?.job_id || "this run");
    if (!window.confirm(`Delete ${label} and its saved reports? This cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.detail || payload.message || "Run could not be deleted");
        }

        runHistory = runHistory.filter((item) => item.job_id !== jobId);
        if (currentJobId === jobId) {
            currentJobId = null;
            clearFiles();
            resetExperience();
        }
        renderRunHistory();
    } catch (error) {
        showError(`Could not delete run: ${error.message}`);
    }
}

function updateFileList() {
    fileItems.innerHTML = "";
    const totalBytes = selectedFiles.reduce((sum, file) => sum + (file.size || 0), 0);

    if (selectedFiles.length === 0) {
        fileList.classList.remove("show");
        selectedSummary.textContent = "0 files selected";
        uploadZone.classList.remove("ready");
        uploadFeedback.classList.remove("show");
        uploadZoneTitle.textContent = "Drop `.eml` files here";
        uploadZoneText.textContent = "or click to browse exported email evidence from disk";
        submitBtn.disabled = !setupConfirmed;
        if (!progressPanel.classList.contains("show") && !resultsPanel.classList.contains("show")) {
            setReviewMode("idle");
        }
        return;
    }

    const invalidFiles = selectedFiles.filter((file) => !file.name.toLowerCase().endsWith(".eml"));
    if (invalidFiles.length > 0) {
        submitBtn.disabled = true;
        fileList.classList.add("show");
        selectedSummary.textContent = `${selectedFiles.length} files selected · ${formatBytes(totalBytes)}`;
        uploadZone.classList.remove("ready");
        uploadFeedback.classList.remove("show");
        uploadZoneTitle.textContent = "Remove unsupported files to continue";
        uploadZoneText.textContent = "Only `.eml` files can be included in the batch.";
        invalidFiles.slice(0, 8).forEach((file) => {
            const item = document.createElement("div");
            item.className = "file-item";
            item.innerHTML = `<span>${escapeHtml(file.name)}</span><strong>Unsupported</strong>`;
            fileItems.appendChild(item);
        });
        fileDetails.open = true;
        showError("The selected batch contains unsupported files. Only `.eml` files can be submitted.");
        return;
    }

    hideError();
    fileList.classList.add("show");
    submitBtn.disabled = !setupConfirmed;
    selectedSummary.textContent = `${selectedFiles.length} files selected · ${formatBytes(totalBytes)}`;
    fileDetails.open = selectedFiles.length <= 10;
    uploadZone.classList.add("ready");
    uploadFeedback.classList.add("show");
    uploadZoneTitle.textContent = `${selectedFiles.length} files ready for review`;
    uploadZoneText.textContent = "Selection accepted. Review can begin as soon as you start the analysis.";
    uploadFeedbackTitle.textContent = "Files accepted for review";
    uploadFeedbackText.textContent = "Selection confirmed. You can start the run whenever you are ready.";
    uploadFeedbackMeta.textContent = `${selectedFiles.length} file${selectedFiles.length === 1 ? "" : "s"} · ${formatBytes(totalBytes)}`;

    selectedFiles.slice(0, 8).forEach((file) => {
        const item = document.createElement("div");
        item.className = "file-item";
        item.innerHTML = `<span>${escapeHtml(file.name)}</span><strong>${formatBytes(file.size)}</strong>`;
        fileItems.appendChild(item);
    });

    if (selectedFiles.length > 8) {
        const item = document.createElement("div");
        item.className = "file-item";
        item.innerHTML = `<span>Additional files</span><strong>+${selectedFiles.length - 8}</strong>`;
        fileItems.appendChild(item);
    }

    if (!progressPanel.classList.contains("show") && !resultsPanel.classList.contains("show")) {
        setReviewMode("idle");
    }
}

function clearFiles() {
    selectedFiles = [];
    fileInput.value = "";
    updateFileList();
}

function startNewReview() {
    stopStatusStreaming();
    currentJobId = null;
    clearFiles();
    resetExperience();
    setView("review");
    renderRunHistory();
}

function resolveUiValue(value, platform) {
    if (!value) {
        return "";
    }
    switch (value) {
        case "__OLLAMA_DOWNLOAD_URL__":
            return platform.ollamaDownloadUrl;
        case "__OLLAMA_INSTALL_COMMAND__":
            return platform.ollamaInstallCommand;
        case "__TESSERACT_INSTALL_COMMAND__":
            return platform.tesseractInstallCommand;
        default:
            return value;
    }
}

function resolveUiAction(action, platform) {
    return {
        ...action,
        value: resolveUiValue(action.value || "", platform),
    };
}

function resolveUiStep(step, platform) {
    return {
        ...step,
        extras: (step.extras || []).map((value) => resolveUiValue(value, platform)),
        actions: (step.actions || []).map((action) => resolveUiAction(action, platform)),
    };
}

function renderWorkspaceGate(gate, platform) {
    const resolvedActions = (gate.actions || []).map((action) => resolveUiAction(action, platform));
    document.getElementById("workspaceGateTitle").textContent = gate.title || "Finish setup before starting a review";
    document.getElementById("workspaceGateText").textContent = gate.detail || "The review workspace stays locked until local runtime, OCR support, and model readiness are confirmed.";
    document.getElementById("workspaceGateActions").innerHTML = resolvedActions.map(renderWizardActionButton).join("");
}

function applyWorkspaceAvailability(payload) {
    const ui = payload?.ui || {};
    const platform = detectPlatform();
    setupConfirmed = !Boolean(ui.workspace_locked);

    workspaceGate.classList.toggle("show", !setupConfirmed);
    uploadZone.classList.toggle("disabled", !setupConfirmed);
    fileInput.disabled = !setupConfirmed;

    if (!setupConfirmed) {
        submitBtn.disabled = true;
        renderWorkspaceGate(ui.workspace_gate || {}, platform);
    } else {
        submitBtn.disabled = selectedFiles.length === 0;
    }
}

function detectPlatform() {
    const platform = (navigator.userAgentData?.platform || navigator.platform || "").toLowerCase();
    if (platform.includes("mac")) {
        return {
            key: "mac",
            label: "macOS",
            ollamaDownloadUrl: "https://ollama.com/download",
            ollamaInstallCommand: "brew install ollama",
            tesseractInstallCommand: "brew install tesseract libmagic",
        };
    }
    if (platform.includes("win")) {
        return {
            key: "windows",
            label: "Windows",
            ollamaDownloadUrl: "https://ollama.com/download/windows",
            ollamaInstallCommand: "Download and run the Ollama installer from ollama.com/download",
            tesseractInstallCommand: "Install Tesseract OCR and ensure it is available on PATH.",
        };
    }
    return {
        key: "linux",
        label: "Linux",
        ollamaDownloadUrl: "https://ollama.com/download/linux",
        ollamaInstallCommand: "curl -fsSL https://ollama.com/install.sh | sh",
        tesseractInstallCommand: "sudo apt-get install -y tesseract-ocr libmagic1",
    };
}

function openExternal(url) {
    window.open(url, "_blank", "noopener,noreferrer");
}

async function copyCommand(command) {
    try {
        await navigator.clipboard.writeText(command);
        showError(`Copied command: ${command}`);
    } catch (error) {
        showError(`Could not copy command automatically. Use this manually: ${command}`);
    }
}

function openStartupWizard(force = false) {
    startupWizardForced = force;
    startupWizard.classList.add("show");
    startupWizard.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
}

function closeStartupWizard() {
    if (!currentSetupStatus?.wizard_ready && !startupWizardForced) {
        return;
    }
    startupWizard.classList.remove("show");
    startupWizard.setAttribute("aria-hidden", "true");
    startupWizardForced = false;
    document.body.style.overflow = "";
}

async function refreshSetupStatus(deep = false, options = {}) {
    const showModal = options.showModal ?? deep;
    const quiet = Boolean(options.quiet);

    try {
        const loadPayload = async () => {
            const response = await fetch(deep ? "/api/setup/system-check" : "/api/setup/status", {
                method: deep ? "POST" : "GET",
            });
            if (!response.ok) {
                throw new Error("Setup status request failed");
            }
            return response.json();
        };

        const payload = showModal
            ? await runWithActivityModal(
                {
                    title: deep ? "Running system check" : "Refreshing setup status",
                    detail: deep
                        ? "Checking OCR dependencies, local runtime health, installed model state, and structured generation support."
                        : "Refreshing local readiness indicators.",
                    label: deep ? "System check in progress" : "Refreshing setup state",
                },
                loadPayload,
            )
            : await loadPayload();

        currentSetupStatus = payload;
        renderSetupStatus(payload);
    } catch (error) {
        if (!quiet) {
            showError(`Setup check failed: ${error.message}`);
        }
    }
}

function renderSetupStatus(payload) {
    const build = payload.build || {};
    currentBuildInfo = {
        build_id: build.build_id,
        build_label: build.build_label,
        html_report_schema_version: build.html_report_schema_version,
        csv_report_schema_version: build.csv_report_schema_version,
        file_review_schema_version: build.file_review_schema_version,
    };

    const task = payload.task || payload.pull || {};
    const ui = payload.ui || {};
    const platform = detectPlatform();
    const ready = !Boolean(ui.workspace_locked);
    const banner = ui.banner || { level: "warn", label: "Checking local setup" };

    const statusPill = document.getElementById("topStatusPill");
    const statusText = document.getElementById("topStatusText");
    statusPill.className = `status-pill ${banner.level || "warn"}`;
    statusText.textContent = banner.label || "Checking local setup";

    document.getElementById("wizardStatusPill").className = statusPill.className;
    document.getElementById("wizardStatusLabel").textContent = statusText.textContent;
    document.getElementById("wizardSummary").textContent = ui.wizard_summary || (
        ready
            ? "Your local runtime, OCR support, and configured model are ready. You can enter the review workspace."
            : "Before using the product, complete the steps below so the local runtime, OCR support, and recommended model are available."
    );

    document.getElementById("recommendedActions").innerHTML = (payload.recommended_actions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    document.getElementById("pullStatus").textContent = task.detail || "No background setup activity has been started.";
    document.getElementById("pullLog").innerHTML = (task.log_tail || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");

    const steps = (ui.wizard_steps || []).map((step) => resolveUiStep(step, platform));
    document.getElementById("wizardSteps").innerHTML = steps.map(renderWizardStep).join("");
    document.getElementById("wizardPrimaryActions").innerHTML = (ui.wizard_primary_actions || [])
        .map((action) => resolveUiAction(action, platform))
        .map(renderWizardActionButton)
        .join("");
    applyWorkspaceAvailability(payload);

    if (ui.wizard_should_open || startupWizardForced) {
        openStartupWizard(false);
    } else {
        closeStartupWizard();
    }

    if (task.status === "running") {
        scheduleSetupPolling();
    } else {
        stopSetupPolling();
    }

    maybeRunAutomaticDeepCheck(payload);
}

function maybeRunAutomaticDeepCheck(payload) {
    if (autoDeepCheckInFlight || !payload?.ui?.auto_deep_check_eligible) {
        return;
    }

    autoDeepCheckInFlight = true;
    refreshSetupStatus(true, { showModal: false, quiet: true })
        .finally(() => {
            autoDeepCheckInFlight = false;
            if (currentSetupStatus) {
                renderSetupStatus(currentSetupStatus);
            }
        });
}

function renderWizardStep(step) {
    const actionHtml = step.actions.length
        ? `<div class="actions">${step.actions.map(renderWizardActionButton).join("")}</div>`
        : "";
    const extrasHtml = step.extras.length
        ? step.extras.map((value) => `<div class="code-chip">${escapeHtml(value)}</div>`).join("")
        : "";
    return `
        <div class="step-card ${step.status}">
            <div>
                <span class="caps">${escapeHtml(step.status === "ok" ? "Ready" : (step.status === "warn" ? "Action needed" : "Blocking setup"))}</span>
                <h3>${escapeHtml(step.title)}</h3>
            </div>
            <p>${escapeHtml(step.detail)}</p>
            ${extrasHtml}
            ${actionHtml}
        </div>
    `;
}

function renderWizardActionButton(action) {
    const styleClass = action.style === "primary"
        ? "btn-primary"
        : (action.style === "tertiary" ? "btn-tertiary" : "btn-secondary");
    const encodedValue = action.value ? encodeURIComponent(action.value) : "";
    return `<button class="${styleClass}" type="button" onclick="runWizardAction('${action.type}', '${encodedValue}')">${escapeHtml(action.label)}</button>`;
}

async function runWizardAction(type, encodedValue) {
    const value = encodedValue ? decodeURIComponent(encodedValue) : "";
    switch (type) {
        case "external":
            openExternal(value);
            break;
        case "copy":
            await copyCommand(value);
            break;
        case "refresh":
            await refreshSetupStatus(value === "deep", { showModal: true });
            break;
        case "start-ollama":
            await startOllamaService();
            break;
        case "pull-model":
            await pullRecommendedModel();
            break;
        case "install-dependency":
            await installDependency(value);
            break;
        case "continue":
            closeStartupWizard();
            setView("review");
            break;
        case "continue-to-wizard":
            openStartupWizard(true);
            break;
        default:
            break;
    }
}

async function startOllamaService() {
    try {
        const payload = await runWithActivityModal(
            {
                title: "Starting Ollama",
                detail: "Launching the local Ollama runtime in the background when possible.",
                label: "Starting local runtime",
            },
            async () => {
                const response = await fetch("/api/setup/start-ollama", { method: "POST" });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.message || "Failed to start Ollama");
                }
                return payload;
            },
        );
        document.getElementById("pullStatus").textContent = payload.message || "Started Ollama.";
        await refreshSetupStatus(false, { showModal: false });
    } catch (error) {
        showError(`Could not start Ollama: ${error.message}`);
    }
}

async function pullRecommendedModel() {
    try {
        const payload = await runWithActivityModal(
            {
                title: "Starting model download",
                detail: "Requesting the local runtime to pull the recommended qwen3:4b model.",
                label: "Submitting model pull request",
            },
            async () => {
                const response = await fetch("/api/setup/pull-model", { method: "POST" });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.message || "Failed to start model pull");
                }
                return payload;
            },
        );
        document.getElementById("pullStatus").textContent = payload.message || "Started model pull.";
        if ((payload.task || payload.pull)?.status === "running") {
            scheduleSetupPolling();
        }
        await refreshSetupStatus(false, { showModal: false });
    } catch (error) {
        showError(`Model pull failed to start: ${error.message}`);
    }
}

async function installDependency(dependency) {
    try {
        const label = dependency === "ollama" ? "Ollama" : "OCR support";
        const payload = await runWithActivityModal(
            {
                title: `Starting ${label} install`,
                detail: `Submitting a local package-manager install for ${label}. This may take a minute and can require additional system permissions outside the browser.`,
                label: `Starting ${label.toLowerCase()} install`,
            },
            async () => {
                const response = await fetch(`/api/setup/install-dependency/${encodeURIComponent(dependency)}`, { method: "POST" });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.message || `Failed to start ${label} install`);
                }
                return payload;
            },
        );
        document.getElementById("pullStatus").textContent = payload.message || `Started ${label} install.`;
        if ((payload.task || payload.pull)?.status === "running") {
            scheduleSetupPolling();
        }
        await refreshSetupStatus(false, { showModal: false });
    } catch (error) {
        showError(`Could not start dependency install: ${error.message}`);
    }
}

function scheduleSetupPolling() {
    if (setupPollIntervalId) {
        return;
    }
    setupPollIntervalId = window.setInterval(() => refreshSetupStatus(false, { showModal: false }), 4000);
}

function stopSetupPolling() {
    if (setupPollIntervalId) {
        window.clearInterval(setupPollIntervalId);
        setupPollIntervalId = null;
    }
}

function startSetupHeartbeat() {
    if (setupHeartbeatIntervalId) {
        return;
    }
    setupHeartbeatIntervalId = window.setInterval(() => {
        if (!document.hidden) {
            refreshSetupStatus(false, { showModal: false, quiet: true });
        }
    }, 30000);
}

function startHistoryHeartbeat() {
    if (historyHeartbeatIntervalId) {
        return;
    }
    historyHeartbeatIntervalId = window.setInterval(() => {
        if (!document.hidden) {
            refreshJobHistory();
        }
    }, 10000);
}

function showActivityModal({ title, detail, label }) {
    activeModalDepth += 1;
    document.getElementById("activityTitle").textContent = title || "Please wait";
    document.getElementById("activityDetail").textContent = detail || "The system is processing your request.";
    document.getElementById("activityLabel").textContent = label || "Working…";
    activityModal.classList.add("show");
    activityModal.setAttribute("aria-hidden", "false");
}

function hideActivityModal() {
    activeModalDepth = Math.max(0, activeModalDepth - 1);
    if (activeModalDepth > 0) {
        return;
    }
    activityModal.classList.remove("show");
    activityModal.setAttribute("aria-hidden", "true");
}

async function runWithActivityModal(copy, action) {
    showActivityModal(copy);
    try {
        return await action();
    } finally {
        hideActivityModal();
    }
}

async function submitFiles() {
    if (selectedFiles.length === 0) return;

    setView("review");
    stopStatusStreaming();
    hideError();
    submitBtn.disabled = true;
    setReviewMode("running");
    document.getElementById("progressFill").style.width = "0%";
    document.getElementById("progressPercent").textContent = "0%";
    document.getElementById("processedCount").textContent = "0";
    document.getElementById("personCount").textContent = "0";
    document.getElementById("jobStatus").textContent = "Uploading";
    document.getElementById("jobPhase").textContent = "Uploading files to the analysis service.";
    document.getElementById("currentFile").textContent = "—";
    document.getElementById("statusText").textContent = "Uploading files for analysis.";
    document.getElementById("progressLabel").textContent = "Upload in progress.";

    try {
        const data = await uploadFilesWithProgress(selectedFiles);
        currentJobId = data.job_id;
        upsertCurrentRunHistory({
            status: "queued",
            progress: {
                processed: 0,
                total: data.file_count || selectedFiles.length,
                current_file: "",
                persons_found: 0,
                message: "Upload accepted. Waiting for the analysis worker.",
            },
            result_available: false,
            summary: null,
        });
        refreshJobHistory();
        document.getElementById("totalCount").textContent = data.file_count;
        document.getElementById("resultFileCount").textContent = data.file_count;
        document.getElementById("jobStatus").textContent = "Processing";
        document.getElementById("jobPhase").textContent = "Upload complete. Connecting to live analysis stream.";
        document.getElementById("statusText").textContent = "Waiting for the scanner to emit progress events.";
        document.getElementById("progressLabel").textContent = "Connecting to live job stream.";
        streamProgress(currentJobId);
    } catch (error) {
        showError(`Upload failed: ${error.message}`);
        submitBtn.disabled = false;
        setReviewMode("idle");
    }
}

function uploadFilesWithProgress(files) {
    return new Promise((resolve, reject) => {
        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/upload");
        xhr.responseType = "json";

        xhr.upload.onprogress = (event) => {
            if (!event.lengthComputable) {
                document.getElementById("jobStatus").textContent = "Uploading";
                document.getElementById("jobPhase").textContent = "Uploading files to the analysis service.";
                document.getElementById("statusText").textContent = "Uploading files for analysis.";
                document.getElementById("progressLabel").textContent = "Upload in progress.";
                return;
            }

            const percent = Math.max(1, Math.round((event.loaded / event.total) * 100));
            document.getElementById("jobStatus").textContent = "Uploading";
            document.getElementById("jobPhase").textContent = `Uploading ${files.length} file${files.length === 1 ? "" : "s"} to the analysis service.`;
            document.getElementById("statusText").textContent = `Upload progress: ${percent}%`;
            document.getElementById("progressLabel").textContent = `${formatBytes(event.loaded)} of ${formatBytes(event.total)} uploaded`;
            document.getElementById("progressFill").style.width = `${percent}%`;
            document.getElementById("progressPercent").textContent = `${percent}%`;
        };

        xhr.onload = () => {
            if (xhr.status < 200 || xhr.status >= 300) {
                reject(new Error(extractApiError(xhr.response) || xhr.statusText || "Upload failed"));
                return;
            }
            resolve(xhr.response);
        };

        xhr.onerror = () => reject(new Error("Network error while uploading files"));
        xhr.send(formData);
    });
}

function streamProgress(jobId) {
    stopStatusStreaming();
    streamHasDeliveredEvent = false;
    currentEventSource = new EventSource(`/api/jobs/${jobId}/stream`);

    streamConnectTimeoutId = window.setTimeout(() => {
        if (!streamHasDeliveredEvent) {
            startStatusPolling(jobId, "Live stream is slow to connect. Falling back to status polling.");
        }
    }, 2500);

    currentEventSource.onmessage = (event) => {
        streamHasDeliveredEvent = true;
        clearStreamConnectTimeout();
        const data = JSON.parse(event.data);

        if (data.type === "progress") {
            applyProgressUpdate(data);
        }

        if (data.type === "complete") {
            stopStatusStreaming();
            showResults(jobId, data);
        }

        if (data.type === "error") {
            stopStatusStreaming();
            showError(`Analysis error: ${data.message}`);
            submitBtn.disabled = false;
            setReviewMode("idle");
        }
    };

    currentEventSource.onerror = () => {
        startStatusPolling(jobId, "Live stream disconnected. Falling back to status polling.");
    };
}

function applyProgressUpdate(data) {
    const percent = data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;
    document.getElementById("progressFill").style.width = `${percent}%`;
    document.getElementById("progressPercent").textContent = `${percent}%`;
    document.getElementById("processedCount").textContent = data.processed;
    document.getElementById("personCount").textContent = data.persons_found || 0;
    document.getElementById("jobStatus").textContent = formatStatus(data.status || "processing");
    document.getElementById("currentFile").textContent = data.current_file || "Phase transition";
    document.getElementById("jobPhase").textContent = data.message || "Scanning messages and attachments.";
    document.getElementById("statusText").textContent = data.message || `Processing ${data.current_file || "uploaded files"}.`;
    document.getElementById("progressLabel").textContent = data.current_file
        ? `Working on ${data.current_file}`
        : (data.message || "Preparing next phase.");
    upsertCurrentRunHistory({
        status: (data.status || "processing"),
        progress: {
            processed: data.processed || 0,
            total: data.total || 0,
            current_file: data.current_file || "",
            persons_found: data.persons_found || 0,
            message: data.message || "",
        },
        result_available: false,
    });
}

async function startStatusPolling(jobId, reason) {
    if (statusPollIntervalId) {
        return;
    }

    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }
    clearStreamConnectTimeout();

    document.getElementById("jobPhase").textContent = reason;
    document.getElementById("statusText").textContent = reason;

    const tick = async () => {
        try {
            const response = await fetch(`/api/jobs/${jobId}/status`);
            if (!response.ok) {
                throw new Error("Status fetch failed");
            }

            const payload = await response.json();
            applyProgressUpdate({
                status: payload.status,
                processed: payload.progress?.processed || 0,
                total: payload.progress?.total || 0,
                current_file: payload.progress?.current_file || "",
                persons_found: payload.progress?.persons_found || 0,
                message: payload.progress?.message || reason,
            });

            if (payload.status === "complete" || payload.result_available) {
                const summaryResponse = await fetch(`/api/jobs/${jobId}/result`);
                if (!summaryResponse.ok) {
                    throw new Error("Final result fetch failed");
                }
                const summary = await summaryResponse.json();
                stopStatusStreaming();
                showResults(jobId, summary);
                return;
            }

            if (payload.status === "error") {
                stopStatusStreaming();
                showError(`Analysis error: ${payload.error || "Unknown error"}`);
                submitBtn.disabled = false;
                setReviewMode("idle");
            }
        } catch (error) {
            stopStatusStreaming();
            showError(`Status update failed: ${error.message}`);
            submitBtn.disabled = false;
            setReviewMode("idle");
        }
    };

    statusPollIntervalId = window.setInterval(tick, 1000);
    await tick();
}

function clearStreamConnectTimeout() {
    if (streamConnectTimeoutId) {
        window.clearTimeout(streamConnectTimeoutId);
        streamConnectTimeoutId = null;
    }
}

function stopStatusStreaming() {
    if (currentEventSource) {
        currentEventSource.close();
        currentEventSource = null;
    }
    if (statusPollIntervalId) {
        window.clearInterval(statusPollIntervalId);
        statusPollIntervalId = null;
    }
    clearStreamConnectTimeout();
    streamHasDeliveredEvent = false;
}

async function showResults(jobId, summary) {
    try {
        validateRunSummary(summary);
    } catch (error) {
        setReviewMode("idle");
        setFileReviewAvailability(false);
        showError(error.message);
        return;
    }

    currentJobId = jobId;
    setReviewMode("complete");
    submitBtn.disabled = false;

    document.getElementById("resultFileCount").textContent = summary.total_files_processed || selectedFiles.length;
    document.getElementById("totalPersonsResult").textContent = summary.persons_found || 0;
    document.getElementById("highRiskResult").textContent = summary.high_risk || 0;
    document.getElementById("mediumRiskResult").textContent = summary.medium_risk || 0;
    document.getElementById("notificationResult").textContent = summary.notification_required || 0;
    document.getElementById("resultRunMeta").textContent = `Build ${summary.build_label} · HTML schema ${summary.html_report_schema_version} · CSV schema ${summary.csv_report_schema_version} · QA schema ${summary.file_review_schema_version}`;
    setFileReviewAvailability(Boolean(summary.file_review_available));
    upsertCurrentRunHistory({
        status: "complete",
        completed_at: new Date().toISOString(),
        result_available: true,
        summary: {
            total_files_processed: summary.total_files_processed || 0,
            persons_found: summary.persons_found || 0,
            high_risk: summary.high_risk || 0,
            medium_risk: summary.medium_risk || 0,
            notification_required: summary.notification_required || 0,
            files_ai_reviewed: summary.files_ai_reviewed || 0,
            files_needing_human_review: summary.files_needing_human_review || 0,
            file_review_available: Boolean(summary.file_review_available),
            build_label: summary.build_label || "",
        },
        progress: {
            processed: summary.total_files_processed || 0,
            total: summary.total_files_processed || 0,
            current_file: "",
            persons_found: summary.persons_found || 0,
            message: "Analysis complete.",
        },
    });
    refreshJobHistory();

    renderPersonTable(summary.persons || []);

    try {
        const response = await fetch(`/api/jobs/${jobId}/report.html`);
        if (!response.ok) {
            throw new Error("Report fetch failed");
        }
        const htmlContent = await response.text();
        displayHtmlReport(htmlContent);
    } catch (error) {
        console.log("HTML report preview unavailable", error);
    }
}

function renderPersonTable(persons) {
    const resultsBody = document.getElementById("resultsBody");
    if (!persons.length) {
        resultsBody.innerHTML = "<tr><td colspan=\"6\">No affected records were resolved for this job.</td></tr>";
        return;
    }

    resultsBody.innerHTML = persons.map((person) => `
        <tr>
            <td>
                <strong>${escapeHtml(person.canonical_name || person.canonical_email || "Unknown record")}</strong><br>
                <span style="color: var(--ink-soft);">${escapeHtml(person.canonical_email || "No canonical email")}</span>
            </td>
            <td>${escapeHtml((person.entity_type || "PERSON").replaceAll("_", " "))}</td>
            <td><span class="risk-chip ${riskClass(person.highest_risk_level)}">${escapeHtml(person.highest_risk_level)}</span></td>
            <td>${person.pii_count || 0}</td>
            <td>${Math.round((person.attribution_confidence || 0) * 100)}%</td>
            <td>${Number(person.risk_score || 0).toFixed(1)}</td>
        </tr>
    `).join("");
}

function displayHtmlReport(htmlContent) {
    const container = document.getElementById("htmlReportContainer");
    const iframe = document.getElementById("htmlReportIframe");
    iframe.srcdoc = htmlContent;
    container.style.display = "block";
    iframe.classList.toggle("collapsed", reportCollapsed);
}

function toggleHtmlReport() {
    const iframe = document.getElementById("htmlReportIframe");
    reportCollapsed = !reportCollapsed;
    iframe.classList.toggle("collapsed", reportCollapsed);
}

function downloadHTML() {
    if (currentJobId) {
        window.location.href = `/api/jobs/${currentJobId}/report.html`;
    }
}

function downloadCSV() {
    if (currentJobId) {
        window.location.href = `/api/jobs/${currentJobId}/report.csv`;
    }
}

function downloadFileReviewCSV() {
    if (currentJobId) {
        if (fileReviewBtn.disabled) {
            showError("AI QA CSV is unavailable for this run. Restart the web server and rerun the analysis.");
            return;
        }
        window.location.href = `/api/jobs/${currentJobId}/file_review.csv`;
    }
}

function resetExperience() {
    stopStatusStreaming();
    setReviewMode("idle");
    hideError();
    submitBtn.disabled = selectedFiles.length === 0;
    if (!selectedFiles.length) {
        fileList.classList.remove("show");
    }
    document.getElementById("htmlReportContainer").style.display = "none";
    document.getElementById("htmlReportIframe").srcdoc = "";
    document.getElementById("resultRunMeta").textContent = "";
    setFileReviewAvailability(false);
    reportCollapsed = false;
}

function validateRunSummary(summary) {
    const requiredKeys = [
        "build_id",
        "build_label",
        "html_report_schema_version",
        "csv_report_schema_version",
        "file_review_schema_version",
        "file_review_expected",
        "file_review_available",
    ];
    const missingKeys = requiredKeys.filter((key) => !(key in summary));
    if (missingKeys.length) {
        throw new Error(
            `The web server returned an outdated result schema (${missingKeys.join(", ")} missing). Restart the analyzer with python run.py and rerun the job.`,
        );
    }

    if (summary.file_review_expected && (!summary.file_review_csv || !summary.file_review_available)) {
        throw new Error(
            "This run is invalid: AI QA output was expected but file_review.csv is missing. Restart the analyzer and rerun the job.",
        );
    }

    if (currentBuildInfo && summary.build_id !== currentBuildInfo.build_id) {
        throw new Error(
            `This run was generated by build ${summary.build_label}, but the current server is ${currentBuildInfo.build_label}. Restart the analyzer and rerun the job to avoid stale report logic.`,
        );
    }
}

function setFileReviewAvailability(available) {
    fileReviewBtn.disabled = !available;
    fileReviewBtn.title = available ? "Download file-level AI QA review export" : "AI QA export unavailable for this run";
}

function showError(message) {
    document.getElementById("errorMessage").textContent = message;
    errorPanel.classList.add("show");
}

function hideError() {
    errorPanel.classList.remove("show");
}

function extractApiError(payload) {
    if (!payload) return "";
    if (typeof payload === "string") return payload;
    if (typeof payload.detail === "string") return payload.detail;
    if (typeof payload.detail?.message === "string") {
        const invalid = Array.isArray(payload.detail.invalid_filenames) && payload.detail.invalid_filenames.length
            ? ` Unsupported: ${payload.detail.invalid_filenames.join(", ")}`
            : "";
        return `${payload.detail.message}${invalid}`;
    }
    if (typeof payload.message === "string") return payload.message;
    return "";
}

function formatStatus(value) {
    const normalized = String(value || "").replaceAll("_", " ").trim();
    if (!normalized) return "Processing";
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function formatBytes(bytes) {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    let index = 0;
    let value = bytes;
    while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
    }
    return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function riskClass(level) {
    const normalized = (level || "").toLowerCase();
    if (normalized === "critical") return "risk-critical";
    if (normalized === "high") return "risk-high";
    if (normalized === "medium") return "risk-medium";
    return "risk-low";
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;")
        .replaceAll("'", "&#39;");
}

window.toggleSidebar = toggleSidebar;
window.setView = setView;
window.startNewReview = startNewReview;
window.submitFiles = submitFiles;
window.clearFiles = clearFiles;
window.openStartupWizard = openStartupWizard;
window.runWizardAction = runWizardAction;
window.resetExperience = resetExperience;
window.downloadHTML = downloadHTML;
window.downloadCSV = downloadCSV;
window.downloadFileReviewCSV = downloadFileReviewCSV;
window.toggleHtmlReport = toggleHtmlReport;
