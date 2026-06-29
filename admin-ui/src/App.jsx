import {
  Activity,
  AlertTriangle,
  Bot,
  ChevronRight,
  CheckCircle2,
  Clock3,
  Database,
  FileClock,
  FileText,
  HardDrive,
  Home,
  Layers3,
  ListChecks,
  MessageCircle,
  PlayCircle,
  Plus,
  RefreshCw,
  Rocket,
  Save,
  Search,
  Server,
  Settings2,
  Square,
  Trash2,
  UploadCloud,
  UsersRound,
  WandSparkles,
  Zap,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import KnowledgeWorkspace from "./KnowledgeWorkspace.jsx";

const sectionMeta = {
  home: { title: "首页", icon: Home, accent: "green" },
  bots: { title: "机器人身份", icon: Bot, accent: "jade" },
  styles: { title: "回复风格", icon: WandSparkles, accent: "cyan" },
  knowledge: { title: "知识库", icon: Database, accent: "amber" },
  bindings: { title: "群绑定", icon: UsersRound, accent: "green" },
  global: { title: "全局设置", icon: Settings2, accent: "slate" },
};

const emptyConfig = {
  botProfiles: [],
  styles: [],
  knowledgeBases: [],
  bindings: [],
  global: {
    excludeGroups: [],
    admins: [],
    cooldownSeconds: 30,
    smartDetection: true,
  },
};

const emptyRuntime = {
  ok: true,
  status: "unknown",
  running: false,
  pid: null,
  dryRun: true,
  listenGroups: [],
  botMentionNames: [],
  lastHeartbeatAt: "",
  lastError: "",
  logFile: "",
  warnings: [],
};

function ensureConfig(config) {
  return {
    ...emptyConfig,
    ...config,
    botProfiles: config?.botProfiles || [],
    styles: config?.styles || [],
    knowledgeBases: config?.knowledgeBases || [],
    bindings: config?.bindings || [],
    global: {
      ...emptyConfig.global,
      ...(config?.global || {}),
    },
  };
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : payload.message || detail?.message || `请求失败：${response.status}`;
    const error = new Error(message);
    error.payload = payload;
    throw error;
  }
  return payload;
}

function lines(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function splitLines(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function classNames(...items) {
  return items.filter(Boolean).join(" ");
}

function defaultBot(config) {
  return {
    id: `bot-${Date.now()}`,
    name: "新机器人",
    role: "负责微信群内的问答和项目判断",
    styleId: config.styles[0]?.id || "",
    answerPolicyId: "strict-kb",
    responsibilities: ["回答群友问题", "根据知识库给出建议"],
    identityPrompt: "你是微信群里的 AI 助手，说话自然、直接、实用。",
  };
}

function defaultStyle() {
  return {
    id: `style-${Date.now()}`,
    name: "新聊天风格",
    tone: "像微信群里的熟人，短句、直接、轻松，不客服腔",
    maxChars: 180,
    emojiPolicy: "少用，只在语气合适时使用",
    avoidWords: ["根据参考资料", "作为AI", "希望这能帮到你"],
    examples: [{ user: "这个靠谱吗？", assistant: "先别急着投。我会先看谁付钱、交付难度和获客是不是稳定。" }],
  };
}

function defaultKnowledgeBase() {
  const id = `kb-${Date.now()}`;
  return {
    id,
    name: "新云知识库",
    description: "用于回答微信群内的相关问题",
    provider: "aliyun_bailian",
    tags: [],
    priority: 0,
    fallbackPolicy: "clarify",
    routeExamples: [],
  };
}

function defaultBinding(config) {
  return {
    group: "",
    botId: config.botProfiles[0]?.id || "",
    knowledgeBaseIds: config.knowledgeBases[0] ? [config.knowledgeBases[0].id] : [],
    replyTriggers: ["?", "？", "#举手"],
  };
}

function duplicateValue(items, field, value, currentIndex) {
  return items.some((item, index) => index !== currentIndex && item[field] === value);
}

function validateGlobal(global) {
  const errors = [];
  const safe = global || {};
  if (!Number.isFinite(Number(safe.cooldownSeconds)) || Number(safe.cooldownSeconds) < 0) {
    errors.push("冷却时间不能小于 0");
  }
  return errors;
}

function validateModalDraft(type, draft, config, currentIndex) {
  const errors = [];
  const idPattern = /^[a-zA-Z0-9_-]+$/;

  if (type === "bots") {
    if (!draft.id?.trim()) errors.push("机器人 ID 必填");
    else if (!idPattern.test(draft.id)) errors.push("机器人 ID 只能用英文、数字、下划线和中划线");
    else if (duplicateValue(config.botProfiles, "id", draft.id, currentIndex)) errors.push("机器人 ID 不能重复");
    if (!draft.name?.trim()) errors.push("机器人名称必填");
    if (!draft.styleId) errors.push("必须绑定一个回复风格");
    else if (!config.styles.some((style) => style.id === draft.styleId)) errors.push("绑定的回复风格不存在");
  }

  if (type === "styles") {
    if (!draft.id?.trim()) errors.push("风格 ID 必填");
    else if (!idPattern.test(draft.id)) errors.push("风格 ID 只能用英文、数字、下划线和中划线");
    else if (duplicateValue(config.styles, "id", draft.id, currentIndex)) errors.push("风格 ID 不能重复");
    if (!draft.name?.trim()) errors.push("风格名称必填");
    if (!draft.tone?.trim()) errors.push("语气说明必填");
    if (!Number.isFinite(Number(draft.maxChars)) || Number(draft.maxChars) <= 0) errors.push("最大字数必须大于 0");
  }

  if (type === "knowledge") {
    if (!draft.id?.trim()) errors.push("知识库 ID 必填");
    else if (!idPattern.test(draft.id)) errors.push("知识库 ID 只能用英文、数字、下划线和中划线");
    else if (duplicateValue(config.knowledgeBases, "id", draft.id, currentIndex)) errors.push("知识库 ID 不能重复");
    if (!draft.name?.trim()) errors.push("知识库名称必填");
    const provider = draft.provider || "aliyun_bailian";
    if (provider !== "aliyun_bailian") errors.push(`暂不支持的知识库类型：${provider}`);
  }

  if (type === "bindings") {
    if (!draft.group?.trim()) errors.push("微信群名必填");
    else if (duplicateValue(config.bindings, "group", draft.group, currentIndex)) errors.push("微信群不能重复绑定");
    if (!draft.botId) errors.push("必须选择一个机器人");
    else if (!config.botProfiles.some((bot) => bot.id === draft.botId)) errors.push("绑定的机器人不存在");
    if (!draft.knowledgeBaseIds?.length) errors.push("至少绑定一个知识库");
    for (const kbId of draft.knowledgeBaseIds || []) {
      if (!config.knowledgeBases.some((kb) => kb.id === kbId)) errors.push(`知识库不存在：${kbId}`);
    }
  }

  return errors;
}

export default function App() {
  const [config, setConfig] = useState(emptyConfig);
  const [backups, setBackups] = useState([]);
  const [active, setActive] = useState("home");
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState(null);
  const [knowledgeViewId, setKnowledgeViewId] = useState("");
  const [status, setStatus] = useState({ tone: "muted", text: "正在连接本地同步服务..." });
  const [saving, setSaving] = useState(false);
  const [runtime, setRuntime] = useState(emptyRuntime);
  const [runtimeBusy, setRuntimeBusy] = useState("");
  const [runtimeLogs, setRuntimeLogs] = useState({
    open: false,
    logFile: "",
    lines: [],
    truncated: false,
  });

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadRuntimeHealth().catch(() => {});
    }, 3000);
    return () => window.clearInterval(timer);
  }, []);

  async function loadAll() {
    setStatus({ tone: "muted", text: "正在读取本地配置..." });
    const [configResponse, backupResponse, runtimeResponse] = await Promise.all([
      requestJson("/api/config"),
      requestJson("/api/backups"),
      requestJson("/api/runtime/health"),
    ]);
    setConfig(ensureConfig(configResponse.config));
    setBackups(backupResponse.backups || []);
    setRuntime({ ...emptyRuntime, ...runtimeResponse });
    setStatus({ tone: "ok", text: "已连接本地同步服务，配置可编辑。" });
  }

  async function reloadBackups() {
    const backupResponse = await requestJson("/api/backups");
    setBackups(backupResponse.backups || []);
  }

  async function saveConfig(nextConfig = config) {
    const errors = validateGlobal(nextConfig.global);
    if (errors.length) {
      setStatus({ tone: "error", text: errors.join("；") });
      return;
    }
    setSaving(true);
    setStatus({ tone: "muted", text: "正在写入本地脚本配置，本地会自动备份旧版本..." });
    try {
      const response = await requestJson("/api/config", {
        method: "POST",
        body: JSON.stringify(nextConfig),
      });
      setConfig(ensureConfig(response.config));
      await reloadBackups();
      setStatus({ tone: "ok", text: "已写入 config/bot.yaml。重启机器人进程后生效。" });
    } finally {
      setSaving(false);
    }
  }

  async function loadRuntimeHealth() {
    const response = await requestJson("/api/runtime/health");
    setRuntime({ ...emptyRuntime, ...response });
    return response;
  }

  async function controlRuntime(action) {
    const labels = {
      start: "启动监听脚本",
      stop: "停止监听脚本",
      restart: "重启监听脚本",
    };
    const payload = action === "stop"
      ? { force: true, timeoutSeconds: 8 }
      : { force: action === "restart" };
    setRuntimeBusy(action);
    setStatus({ tone: "muted", text: `正在${labels[action]}...` });
    try {
      const response = await requestJson(`/api/runtime/${action}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setRuntime({ ...emptyRuntime, ...response });
      setStatus({ tone: "ok", text: response.message || `${labels[action]}已提交。` });
      await loadRuntimeHealth();
    } finally {
      setRuntimeBusy("");
    }
  }

  async function loadRuntimeLogs() {
    const response = await requestJson("/api/runtime/logs?limit=240");
    setRuntimeLogs({
      open: true,
      logFile: response.logFile || "",
      lines: response.lines || [],
      truncated: Boolean(response.truncated),
    });
  }

  function patchGlobal(field, value) {
    setConfig((current) => ({
      ...current,
      global: { ...current.global, [field]: value },
    }));
    setStatus({ tone: "muted", text: "已更新页面配置，点击保存到脚本配置后写入本地。" });
  }

  function openModal(type, index = null) {
    if (type === "knowledge") {
      const item = getItem(type, index);
      setKnowledgeViewId(item?.id || "");
      return;
    }
    const item = getItem(type, index);
    setModal({ type, index, draft: structuredClone(item), error: "" });
  }

  function getItem(type, index) {
    const map = {
      bots: config.botProfiles,
      styles: config.styles,
      knowledge: config.knowledgeBases,
      bindings: config.bindings,
    };
    return map[type][index];
  }

  function addItem(type) {
    const next = structuredClone(config);
    if (type === "bots") next.botProfiles.push(defaultBot(next));
    if (type === "styles") next.styles.push(defaultStyle());
    if (type === "knowledge") next.knowledgeBases.push(defaultKnowledgeBase());
    if (type === "bindings") next.bindings.push(defaultBinding(next));
    setConfig(next);
    const arrays = {
      bots: next.botProfiles,
      styles: next.styles,
      knowledge: next.knowledgeBases,
      bindings: next.bindings,
    };
    if (type === "knowledge") {
      setActive("knowledge");
      setKnowledgeViewId(arrays.knowledge.at(-1).id);
      return;
    }
    openModalFromDraft(type, arrays[type].length - 1, arrays[type].at(-1));
  }

  function openModalFromDraft(type, index, draft) {
    setModal({ type, index, draft: structuredClone(draft), error: "" });
  }

  function removeItem(type, index) {
    const confirmed = window.confirm(
      type === "knowledge"
        ? "确认删除这条知识库配置？此操作只会从本地配置移除，不会删除云端知识库和文档；保存配置后生效。"
        : "确认删除这条配置？删除后还需要保存才会写入本地。",
    );
    if (!confirmed) return;
    const next = structuredClone(config);
    if (type === "bots") next.botProfiles.splice(index, 1);
    if (type === "styles") next.styles.splice(index, 1);
    if (type === "knowledge") next.knowledgeBases.splice(index, 1);
    if (type === "bindings") next.bindings.splice(index, 1);
    setConfig(next);
    if (type === "knowledge") setKnowledgeViewId("");
    setStatus({ tone: "muted", text: "已从页面移除，点击保存到脚本配置后写入本地。" });
  }

  async function saveKnowledgeDraft(originalId, draft) {
    const index = config.knowledgeBases.findIndex((item) => item.id === originalId);
    if (index < 0) throw new Error("知识库配置不存在，请返回列表后重试。");
    const errors = validateModalDraft("knowledge", draft, config, index);
    if (errors.length) throw new Error(errors.join("；"));
    const next = structuredClone(config);
    next.knowledgeBases[index] = { ...next.knowledgeBases[index], ...draft };
    setConfig(next);
    setKnowledgeViewId(draft.id);
    setStatus({ tone: "muted", text: "知识库设置已更新到页面，点击保存配置后写入本地。" });
  }

  function saveModalDraft() {
    if (!modal) return;
    const errors = validateModalDraft(modal.type, modal.draft, config, modal.index);
    if (errors.length) {
      setModal((current) => ({ ...current, error: errors.join("；") }));
      return;
    }

    const next = structuredClone(config);
    if (modal.type === "bots") next.botProfiles[modal.index] = modal.draft;
    if (modal.type === "styles") next.styles[modal.index] = modal.draft;
    if (modal.type === "knowledge") next.knowledgeBases[modal.index] = { ...next.knowledgeBases[modal.index], ...modal.draft };
    if (modal.type === "bindings") next.bindings[modal.index] = modal.draft;
    setConfig(next);
    setModal(null);
    setStatus({ tone: "muted", text: "详情已通过校验并更新到页面，点击保存到脚本配置后写入本地。" });
  }

  async function provisionKnowledge(draft, selectedFiles) {
    if (!selectedFiles.length) throw new Error("请至少选择一个知识库文档。");
    const form = new FormData();
    form.append("knowledge_base", JSON.stringify(draft));
    selectedFiles.forEach((file) => form.append("files", file));
    setStatus({
      tone: "muted",
      text: draft.configured
        ? "正在上传并处理新增文档..."
        : "正在上传文档并创建知识库...",
    });
    const response = await requestJson("/api/knowledge/provision", {
      method: "POST",
      body: form,
    });
    setConfig(ensureConfig(response.config));
    setStatus({ tone: "success", text: response.message });
    return response;
  }

  async function listKnowledgeDocuments(kbId) {
    return requestJson(`/api/knowledge/${kbId}/documents`);
  }

  async function refreshKnowledgeJob(kbId) {
    const response = await requestJson(`/api/knowledge/${kbId}/job`);
    if (response.config) setConfig(ensureConfig(response.config));
    return response;
  }

  async function replaceKnowledgeDocument(kbId, documentId, file) {
    const form = new FormData();
    form.append("file", file);
    setStatus({ tone: "muted", text: "正在上传并替换文档..." });
    const response = await requestJson(
      `/api/knowledge/${kbId}/documents/${documentId}/replace`,
      { method: "POST", body: form },
    );
    setConfig(ensureConfig(response.config));
    setStatus({ tone: "success", text: response.message });
    return response;
  }

  async function deleteKnowledgeDocument(kbId, documentId) {
    const response = await requestJson(
      `/api/knowledge/${kbId}/documents/${documentId}`,
      { method: "DELETE" },
    );
    setConfig(ensureConfig(response.config));
    setStatus({ tone: "success", text: response.message });
    return response;
  }

  const stats = useMemo(() => {
    return [
      { label: "机器人", value: config.botProfiles.length },
      { label: "风格", value: config.styles.length },
      { label: "云知识库", value: config.knowledgeBases.length },
      { label: "群绑定", value: config.bindings.length },
    ];
  }, [config]);

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = {
      bots: config.botProfiles,
      styles: config.styles,
      knowledge: config.knowledgeBases,
      bindings: config.bindings,
    }[active] || [];
    if (!q) return base.map((item, index) => ({ item, index }));
    return base
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => JSON.stringify(item).toLowerCase().includes(q));
  }, [active, config, query]);

  const ActiveIcon = sectionMeta[active].icon;
  const isHome = active === "home";

  function createFromHome(type) {
    setActive(type);
    addItem(type);
  }

  function navigateSection(type) {
    setActive(type);
    if (type === "knowledge") setKnowledgeViewId("");
  }

  return (
    <div className="app-shell">
      <aside className="side-rail">
        <div className="brand">
          <div className="brand-mark">
            <MessageCircle size={25} />
          </div>
          <div>
            <strong>群聊机器人</strong>
            <span>Local Sync Console</span>
          </div>
        </div>

        <nav className="nav-list">
          {Object.entries(sectionMeta).map(([key, meta]) => {
            const Icon = meta.icon;
            return (
              <button
                key={key}
                type="button"
                className={classNames("nav-item", active === key && "is-active")}
                onClick={() => navigateSection(key)}
              >
                <Icon size={18} />
                <span>{meta.title}</span>
              </button>
            );
          })}
        </nav>

        <div className="side-actions">
          <button
            type="button"
            className="side-save-button"
            disabled={isHome || saving}
            title={isHome ? "首页没有可保存的配置，请先进入具体配置页" : "把当前页面配置写入本地 config/bot.yaml，并自动备份旧配置；机器人进程需重启后生效。"}
            onClick={() => saveConfig().catch(showError)}
          >
            <Save size={16} />
            {saving ? "写入中..." : "保存配置"}
          </button>
          <div className="runtime-mini-panel">
            <div className="runtime-mini-status">
              <span className={classNames("runtime-dot", runtime.running && "is-running", runtime.status === "error" && "is-error")} />
              <div>
                <strong>{runtimeStatusText(runtime)}</strong>
                <em>{runtimeDetailText(runtime)}</em>
              </div>
            </div>
            <div className="runtime-action-grid">
              <button
                type="button"
                className="runtime-action-button start"
                disabled={saving || Boolean(runtimeBusy) || runtime.running}
                title="按当前配置启动微信监听和自动回复脚本"
                onClick={() => controlRuntime("start").catch(showError)}
              >
                <PlayCircle size={15} />
                {runtimeBusy === "start" ? "启动中" : "启动"}
              </button>
              <button
                type="button"
                className="runtime-action-button stop"
                disabled={saving || Boolean(runtimeBusy) || !runtime.pid}
                title="停止当前 PID 文件记录的机器人监听进程"
                onClick={() => controlRuntime("stop").catch(showError)}
              >
                <Square size={14} />
                {runtimeBusy === "stop" ? "停止中" : "停止"}
              </button>
              <button
                type="button"
                className="runtime-action-button"
                disabled={saving || Boolean(runtimeBusy)}
                title="停止旧监听进程并按当前配置重新启动"
                onClick={() => controlRuntime("restart").catch(showError)}
              >
                <RefreshCw size={15} />
                {runtimeBusy === "restart" ? "重启中" : "重启"}
              </button>
              <button
                type="button"
                className="runtime-action-button"
                disabled={Boolean(runtimeBusy)}
                title="查看最近的机器人运行日志"
                onClick={() => loadRuntimeLogs().catch(showError)}
              >
                <FileText size={15} />
                日志
              </button>
            </div>
          </div>
        </div>

        <div className={`sync-card tone-${status.tone}`}>
          <span className="sync-status-dot" />
          <div>
            <strong>
              {status.tone === "ok"
                ? "已连接同步服务"
                : status.tone === "error"
                ? "同步服务异常"
                : "正在连接同步服务"}
            </strong>
            <span>{status.text}</span>
          </div>
        </div>
      </aside>

      <main className="main-panel">
        {isHome ? (
          <HomePage
            stats={stats}
            config={config}
            backups={backups}
            runtime={runtime}
            onNavigate={navigateSection}
            onCreate={createFromHome}
          />
        ) : (
          active === "knowledge" ? (
            <KnowledgeWorkspace
              items={visibleItems}
              knowledgeBases={config.knowledgeBases}
              bindings={config.bindings}
              query={query}
              selectedId={knowledgeViewId}
              onQueryChange={setQuery}
              onCreate={() => addItem("knowledge")}
              onSelect={setKnowledgeViewId}
              onBack={() => setKnowledgeViewId("")}
              onRemove={(index) => removeItem("knowledge", index)}
              onSaveDraft={saveKnowledgeDraft}
              onProvision={provisionKnowledge}
              onRefreshJob={refreshKnowledgeJob}
              onListDocuments={listKnowledgeDocuments}
              onReplaceDocument={replaceKnowledgeDocument}
              onDeleteDocument={deleteKnowledgeDocument}
              onNavigateBindings={() => {
                setKnowledgeViewId("");
                setActive("bindings");
              }}
            />
          ) : (
          <section className="content-panel config-only">
            <div className="panel-head">
              <div className="panel-title">
                <div className={`title-icon ${sectionMeta[active].accent}`}>
                  <ActiveIcon size={19} />
                </div>
                <div>
                  <h2>{sectionMeta[active].title}</h2>
                  <p>{getSectionHint(active)}</p>
                </div>
              </div>
              {active !== "global" && (
                <div className="panel-tools">
                  <label className="search-box">
                    <Search size={16} />
                    <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索当前列表" />
                  </label>
                  <button type="button" className="primary-button slim" onClick={() => addItem(active)}>
                    <Plus size={17} />
                    新增
                  </button>
                </div>
              )}
            </div>

            {active === "global" ? (
              <div className="panel-form">
                <p className="panel-form-hint">
                  直接修改下方字段，点击左侧“保存配置”写入本地 <code>config/bot.yaml</code>，重启机器人进程后生效。
                </p>
                <GlobalForm draft={config.global} patch={patchGlobal} />
              </div>
            ) : (
              <ConfigList
                type={active}
                items={visibleItems}
                config={config}
                onEdit={openModal}
                onRemove={removeItem}
              />
            )}
          </section>
          )
        )}
      </main>

      {modal && (
        <DetailModal
          modal={modal}
          config={config}
          setModal={setModal}
          onClose={() => setModal(null)}
          onSave={saveModalDraft}
        />
      )}
      {runtimeLogs.open && (
        <RuntimeLogDrawer
          logs={runtimeLogs}
          onRefresh={() => loadRuntimeLogs().catch(showError)}
          onClose={() => setRuntimeLogs((current) => ({ ...current, open: false }))}
        />
      )}
    </div>
  );

  function showError(error) {
    const payload = error.payload || {};
    if (payload.status || payload.running !== undefined) {
      setRuntime((current) => ({ ...current, ...payload }));
    }
    const checks = Array.isArray(payload.blockingChecks) ? payload.blockingChecks : [];
    const suffix = checks.length
      ? `：${checks.map((item) => item.message || item.code).join("；")}`
      : "";
    setStatus({ tone: "error", text: `${error.message || String(error)}${suffix}` });
  }

}

function getSectionHint(type) {
  return {
    home: "配置总览和本地同步状态。",
    bots: "定义机器人身份、职责和要绑定的回复风格。",
    styles: "控制聊天口吻、禁用表达、示例问答和回复长度。",
    knowledge: "配置阿里云百炼 Workspace、Index、标签和未命中策略。",
    bindings: "把微信群、机器人、知识库和触发词组合起来。",
    global: "冷却时间、智能检测、排除群和管理员名单。",
  }[type];
}

function parseTime(value) {
  const time = Date.parse(value || "");
  return Number.isFinite(time) ? time : 0;
}

function formatTime(value) {
  if (!value) return "暂无时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function runtimeStatusText(runtime) {
  if (runtime?.running) return "运行中";
  if (runtime?.status === "starting") return "启动中";
  if (runtime?.status === "stopped") return "已停止";
  if (runtime?.status === "exited") return "已退出";
  if (runtime?.status === "error" || runtime?.status === "failed") return "异常";
  return "未启动";
}

function runtimeDetailText(runtime) {
  if (runtime?.lastError) return runtime.lastError;
  if (runtime?.pid) return `PID ${runtime.pid}`;
  if (runtime?.logFile) return runtime.logFile;
  return "等待从页面启动监听脚本";
}

function compactList(items, emptyText = "未配置") {
  const safe = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!safe.length) return emptyText;
  return safe.slice(0, 3).join("、") + (safe.length > 3 ? ` 等 ${safe.length} 个` : "");
}

function formatSize(value) {
  const size = Number(value || 0);
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} B`;
}

function percent(done, total) {
  if (!total) return 0;
  return Math.round((done / total) * 100);
}

function buildHomeModel(config, backups) {
  const safeConfig = ensureConfig(config);
  const styles = new Set(safeConfig.styles.map((item) => item.id));
  const bots = new Set(safeConfig.botProfiles.map((item) => item.id));
  const knowledgeBases = new Set(safeConfig.knowledgeBases.map((item) => item.id));
  const botWithStyle = safeConfig.botProfiles.filter((bot) => bot.styleId && styles.has(bot.styleId)).length;
  const bindingWithBot = safeConfig.bindings.filter((binding) => binding.botId && bots.has(binding.botId)).length;
  const bindingWithKb = safeConfig.bindings.filter((binding) =>
    (binding.knowledgeBaseIds || []).some((kbId) => knowledgeBases.has(kbId)),
  ).length;
  const kbWithSources = safeConfig.knowledgeBases.filter((kb) => kb.configured).length;

  const completeness = [
    { label: "机器人已绑定风格", done: botWithStyle, total: safeConfig.botProfiles.length },
    { label: "群已绑定机器人", done: bindingWithBot, total: safeConfig.bindings.length },
    { label: "群已绑定知识库", done: bindingWithKb, total: safeConfig.bindings.length },
    { label: "云知识库配置完整", done: kbWithSources, total: safeConfig.knowledgeBases.length },
  ].map((item) => ({ ...item, value: percent(item.done, item.total) }));
  const totalDone = completeness.reduce((sum, item) => sum + item.done, 0);
  const total = completeness.reduce((sum, item) => sum + item.total, 0);
  const score = percent(totalDone, total);

  const warnings = [];
  if (!safeConfig.botProfiles.length) warnings.push({ title: "还没有机器人身份", detail: "先新建机器人身份，再绑定风格和群。" });
  if (!safeConfig.styles.length) warnings.push({ title: "还没有回复风格", detail: "缺少风格时，机器人很难保持统一口吻。" });
  if (!safeConfig.knowledgeBases.length) warnings.push({ title: "还没有知识库", detail: "知识库为空时，脚本只能走兜底回复。" });
  if (!safeConfig.bindings.length) warnings.push({ title: "还没有群绑定", detail: "没有群绑定时，微信群消息不会路由到机器人。" });

  safeConfig.botProfiles
    .filter((bot) => !bot.styleId || !styles.has(bot.styleId))
    .slice(0, 2)
    .forEach((bot) => warnings.push({ title: `${bot.name || bot.id} 缺少有效风格`, detail: "到机器人身份里绑定一个回复风格。" }));

  safeConfig.bindings
    .filter((binding) => !binding.botId || !bots.has(binding.botId))
    .slice(0, 2)
    .forEach((binding) => warnings.push({ title: `${binding.group || "未命名群"} 缺少有效机器人`, detail: "到群绑定里选择存在的机器人。" }));

  safeConfig.bindings
    .filter((binding) => !(binding.knowledgeBaseIds || []).some((kbId) => knowledgeBases.has(kbId)))
    .slice(0, 2)
    .forEach((binding) => warnings.push({ title: `${binding.group || "未命名群"} 缺少有效知识库`, detail: "至少绑定一个存在的知识库。" }));

  safeConfig.knowledgeBases
    .filter((kb) => !kb.configured)
    .slice(0, 2)
    .forEach((kb) => warnings.push({
      title: `${kb.name || kb.id} 尚未上传文档`,
      detail: "进入知识库详情上传第一批文档，系统会自动创建云知识库。",
    }));

  const recentItems = [
    ...(backups || []).map((item) => ({
      kind: "配置备份",
      title: item.name,
      detail: `${formatSize(item.size)} · ${item.path}`,
      modifiedAt: item.modifiedAt,
      icon: FileClock,
    })),
  ]
    .sort((a, b) => parseTime(b.modifiedAt) - parseTime(a.modifiedAt))
    .slice(0, 6);

  return {
    completeness,
    recentItems,
    score,
    warnings: warnings.slice(0, 7),
  };
}

function HomePage({ stats, config, backups, runtime, onNavigate, onCreate }) {
  const model = useMemo(() => buildHomeModel(config, backups), [config, backups]);
  const quickActions = [
    { title: "新建机器人", desc: "定义身份、职责、回答边界", icon: Bot, action: () => onCreate("bots") },
    { title: "新建风格", desc: "配置像真人一样的口吻", icon: WandSparkles, action: () => onCreate("styles") },
    { title: "接入云知识库", desc: "新建知识库并上传第一批文档", icon: Database, action: () => onCreate("knowledge") },
    { title: "绑定微信群", desc: "选择机器人、知识库和触发词", icon: MessageCircle, action: () => onCreate("bindings") },
  ];
  const scriptSteps = [
    { title: "平台录入", desc: "用户在页面填写机器人、风格、云知识库和群绑定。", icon: UploadCloud },
    { title: "保存配置", desc: "点击保存机器人配置，写入本地 config/bot.yaml。", icon: HardDrive },
    { title: "本地备份", desc: "旧配置自动进入 config/backups，便于回滚。", icon: FileClock },
    { title: "重启机器人", desc: "启动或重启 python -m ai_ta_bot，让机器人读取新配置。", icon: PlayCircle },
    { title: "群聊回复", desc: "微信群消息命中绑定后，检索云知识库并生成回复。", icon: Zap },
  ];

  return (
    <div className="home-stack">
      <article className="home-panel script-panel">
        <div className="home-panel-head">
          <div>
            <span>脚本使用流程图</span>
            <strong>从页面配置到微信群回复</strong>
          </div>
          <Server size={20} />
        </div>
        <div className="script-flow" aria-label="脚本使用流程图">
          {scriptSteps.map((step, index) => {
            const Icon = step.icon;
            return (
              <div className="script-flow-cell" key={step.title}>
                <div className="flow-node">
                  <div className="flow-node-icon">
                    <Icon size={19} />
                  </div>
                  <span>0{index + 1}</span>
                  <strong>{step.title}</strong>
                  <p>{step.desc}</p>
                </div>
                {index < scriptSteps.length - 1 && (
                  <div className="flow-arrow">
                    <ChevronRight size={18} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </article>

      <section className="home-metrics-grid">
        {stats.map((item) => (
          <div className="home-metric-tile" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
      </section>

      <section className="home-command-grid">
        <article className="home-panel status-panel">
          <div className="home-panel-head">
            <div>
              <span>运行状态</span>
              <strong>本地脚本控制面</strong>
            </div>
            <Activity size={20} />
          </div>
          <div className="status-grid">
            <div className="status-item primary">
              <span>监听脚本</span>
              <strong>{runtimeStatusText(runtime)}</strong>
              <em>{runtimeDetailText(runtime)}</em>
            </div>
            <div className="status-item">
              <span>发送模式</span>
              <strong>{runtime?.dryRun ? "DRY_RUN" : "真实发送"}</strong>
              <em>{runtime?.dryRun ? "只生成回复，不发送到微信群" : "会向已监听群发送回复"}</em>
            </div>
            <div className="status-item">
              <span>监听群</span>
              <strong>{Array.isArray(runtime?.listenGroups) ? runtime.listenGroups.length : 0} 个</strong>
              <em>{compactList(runtime?.listenGroups)}</em>
            </div>
            <div className="status-item">
              <span>最近心跳</span>
              <strong>{runtime?.lastHeartbeatAt ? formatTime(runtime.lastHeartbeatAt) : "暂无"}</strong>
              <em>{runtime?.lastError || "未收到运行错误"}</em>
            </div>
          </div>
        </article>

        <article className="home-panel completeness-panel">
          <div className="home-panel-head">
            <div>
              <span>配置完整度</span>
              <strong>能否跑通群聊链路</strong>
            </div>
            <ListChecks size={20} />
          </div>
          <div className="score-row">
            <div className="score-ring" style={{ "--score": `${model.score}%` }}>
              <strong>{model.score}%</strong>
              <span>完成</span>
            </div>
            <div className="completeness-list">
              {model.completeness.map((item) => (
                <div className="progress-line" key={item.label}>
                  <div>
                    <span>{item.label}</span>
                    <em>{item.done}/{item.total}</em>
                  </div>
                  <i><b style={{ width: `${item.value}%` }} /></i>
                </div>
              ))}
            </div>
          </div>
        </article>

        <article className="home-panel recent-panel">
          <div className="home-panel-head">
            <div>
              <span>最近变更</span>
              <strong>配置文件自动备份</strong>
            </div>
            <Clock3 size={20} />
          </div>
          <div className="recent-list">
            {model.recentItems.length ? (
              model.recentItems.map((item) => {
                const Icon = item.icon;
                return (
                  <div className="recent-item" key={`${item.kind}-${item.title}-${item.modifiedAt}`}>
                    <Icon size={17} />
                    <div>
                      <strong>{item.title}</strong>
                      <span>{item.kind} · {formatTime(item.modifiedAt)}</span>
                      <em>{item.detail}</em>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="panel-empty">暂无配置备份。</div>
            )}
          </div>
        </article>

        <article className="home-panel quick-panel">
          <div className="home-panel-head">
            <div>
              <span>快速入口</span>
              <strong>直接进入配置动作</strong>
            </div>
            <Rocket size={20} />
          </div>
          <div className="quick-grid">
            {quickActions.map((item) => {
              const Icon = item.icon;
              return (
                <button type="button" className="quick-action-card" key={item.title} onClick={item.action}>
                  <Icon size={20} />
                  <strong>{item.title}</strong>
                  <span>{item.desc}</span>
                </button>
              );
            })}
          </div>
        </article>

        <article className="home-panel risk-panel">
          <div className="home-panel-head">
            <div>
              <span>风险提醒</span>
              <strong>保存前重点检查</strong>
            </div>
            <AlertTriangle size={20} />
          </div>
          <div className="risk-list">
            {model.warnings.length ? (
              model.warnings.map((item) => (
                <button
                  type="button"
                  className="risk-item"
                  key={`${item.title}-${item.detail}`}
                  onClick={() => onNavigate(item.title.includes("风格") ? "styles" : item.title.includes("知识库") || item.title.includes("文件") ? "knowledge" : item.title.includes("群") ? "bindings" : "bots")}
                >
                  <AlertTriangle size={16} />
                  <span>
                    <strong>{item.title}</strong>
                    <em>{item.detail}</em>
                  </span>
                </button>
              ))
            ) : (
              <div className="risk-item ok">
                <CheckCircle2 size={17} />
                <span>
                  <strong>暂无明显配置风险</strong>
                  <em>保存后重启机器人脚本即可读取最新配置。</em>
                </span>
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
}

function ConfigList({ type, items, config, onEdit, onRemove }) {
  if (!items.length) {
    return (
      <div className="empty-state">
        <Layers3 size={38} />
        <strong>当前列表为空</strong>
        <span>点击右上角新增，创建第一条配置。</span>
      </div>
    );
  }

  return (
    <div className="item-list">
      {items.map(({ item, index }) => (
        <div
          className="list-row"
          key={`${type}-${index}-${item.id || item.group}`}
          role="button"
          tabIndex={0}
          onClick={() => onEdit(type, index)}
          onKeyDown={(event) => {
            if (event.key === "Enter") onEdit(type, index);
          }}
        >
          <div className="row-leading">{renderAvatar(type, item)}</div>
          <div className="row-main">
            <strong>{getTitle(type, item)}</strong>
            <span>{getSubtitle(type, item, config)}</span>
            <div className="chip-line">{getChips(type, item, config).map((chip) => <em key={chip}>{chip}</em>)}</div>
          </div>
          <div className="row-actions" onClick={(event) => event.stopPropagation()}>
            <button type="button" className="icon-danger" onClick={() => onRemove(type, index)} aria-label="删除">
              <Trash2 size={17} />
            </button>
            <ChevronRight size={19} />
          </div>
        </div>
      ))}
    </div>
  );
}

function renderAvatar(type, item) {
  if (type === "bots") return <Bot size={22} />;
  if (type === "styles") return <WandSparkles size={22} />;
  return <MessageCircle size={22} />;
}

function getTitle(type, item) {
  if (type === "bindings") return item.group || "未命名微信群";
  return item.name || item.id || "未命名配置";
}

function getSubtitle(type, item, config) {
  if (type === "bots") return item.role || "未填写角色定位";
  if (type === "styles") return item.tone || "未填写风格说明";
  if (type === "bindings") {
    const bot = config.botProfiles.find((profile) => profile.id === item.botId);
    return `机器人：${bot?.name || item.botId || "未绑定"}`;
  }
  return "";
}

function getChips(type, item, config) {
  if (type === "bots") return [item.id, `风格 ${item.styleId || "未绑定"}`].filter(Boolean);
  if (type === "styles") return [`${item.maxChars || 0} 字以内`, `${item.examples?.length || 0} 个示例`];
  if (type === "bindings") {
    return [
      ...(item.knowledgeBaseIds || []).map((kbId) => config.knowledgeBases.find((kb) => kb.id === kbId)?.name || kbId),
      `${item.replyTriggers?.length || 0} 个触发词`,
    ].slice(0, 5);
  }
  return [];
}

function RuntimeLogDrawer({ logs, onRefresh, onClose }) {
  return (
    <div className="drawer-backdrop runtime-log-backdrop" role="presentation">
      <aside className="runtime-log-drawer" role="dialog" aria-modal="true">
        <div className="drawer-head">
          <div>
            <span>Runtime Logs</span>
            <h2>机器人监听日志</h2>
            <p>{logs.logFile || "还没有生成运行日志。"}</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭">
            <X size={19} />
          </button>
        </div>
        <div className="runtime-log-body">
          {logs.truncated && <div className="runtime-log-note">仅显示最近 240 行。</div>}
          {logs.lines.length ? (
            <pre>{logs.lines.join("\n")}</pre>
          ) : (
            <div className="panel-empty">暂无日志内容。</div>
          )}
        </div>
        <div className="drawer-foot">
          <button type="button" className="ghost-button" onClick={onRefresh}>
            <RefreshCw size={16} />
            刷新日志
          </button>
        </div>
      </aside>
    </div>
  );
}

function DetailModal({
  modal,
  config,
  setModal,
  onClose,
  onSave,
}) {
  const meta = sectionMeta[modal.type];
  const Icon = meta.icon;

  function patch(field, value) {
    setModal(function(current) { return { ...current, draft: { ...current.draft, [field]: value } }; });
  }

  function patchExample(index, field, value) {
    setModal(function(current) {
      var examples = (current.draft.examples || []).slice();
      examples[index] = { ...examples[index], [field]: value };
      return { ...current, draft: { ...current.draft, examples } };
    });
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="detail-modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <div className={"modal-icon " + meta.accent}>
            <Icon size={21} />
          </div>
          <div>
            <h2>{meta.title}详情</h2>
            <p>这里会先校验当前配置项；通过后再回到页面，最后统一保存到脚本配置。</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭">
            <X size={19} />
          </button>
        </div>

        <div className="modal-body">
          {modal.error && <div className="modal-error">{modal.error}</div>}
          {modal.type === "bots" && <BotForm draft={modal.draft} config={config} patch={patch} />}
          {modal.type === "styles" && (
            <StyleForm draft={modal.draft} patch={patch} patchExample={patchExample} setModal={setModal} />
          )}
          {modal.type === "bindings" && <BindingForm draft={modal.draft} config={config} patch={patch} />}
        </div>

        <div className="modal-foot">
          <button type="button" className="ghost-button" onClick={onClose}>取消</button>
          <button type="button" className="primary-button" onClick={onSave}>校验并保存详情</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children, wide = false }) {
  return (
    <label className={classNames("field", wide && "wide")}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function BotForm({ draft, config, patch }) {
  return (
    <div className="form-grid">
      <Field label="ID"><input value={draft.id || ""} onChange={(e) => patch("id", e.target.value)} /></Field>
      <Field label="名称"><input value={draft.name || ""} onChange={(e) => patch("name", e.target.value)} /></Field>
      <Field label="绑定风格">
        <select value={draft.styleId || ""} onChange={(e) => patch("styleId", e.target.value)}>
          <option value="">请选择风格</option>
          {config.styles.map((style) => <option key={style.id} value={style.id}>{style.name || style.id}</option>)}
        </select>
      </Field>
      <Field label="回答策略"><input value={draft.answerPolicyId || ""} onChange={(e) => patch("answerPolicyId", e.target.value)} /></Field>
      <Field label="角色定位" wide><input value={draft.role || ""} onChange={(e) => patch("role", e.target.value)} /></Field>
      <Field label="职责，一行一个" wide>
        <textarea value={lines(draft.responsibilities)} onChange={(e) => patch("responsibilities", splitLines(e.target.value))} />
      </Field>
      <Field label="身份提示词" wide>
        <textarea value={draft.identityPrompt || ""} onChange={(e) => patch("identityPrompt", e.target.value)} />
      </Field>
    </div>
  );
}

function StyleForm({ draft, patch, patchExample, setModal }) {
  return (
    <div className="form-grid">
      <Field label="ID"><input value={draft.id || ""} onChange={(e) => patch("id", e.target.value)} /></Field>
      <Field label="名称"><input value={draft.name || ""} onChange={(e) => patch("name", e.target.value)} /></Field>
      <Field label="最大字数"><input type="number" value={draft.maxChars || 180} onChange={(e) => patch("maxChars", Number(e.target.value))} /></Field>
      <Field label="表情策略"><input value={draft.emojiPolicy || ""} onChange={(e) => patch("emojiPolicy", e.target.value)} /></Field>
      <Field label="语气" wide><input value={draft.tone || ""} onChange={(e) => patch("tone", e.target.value)} /></Field>
      <Field label="禁用表达，一行一个" wide>
        <textarea value={lines(draft.avoidWords)} onChange={(e) => patch("avoidWords", splitLines(e.target.value))} />
      </Field>
      <div className="wide sub-editor">
        <div className="sub-head">
          <strong>风格示例</strong>
          <button
            type="button"
            className="ghost-button slim"
            onClick={() => setModal((current) => ({
              ...current,
              draft: { ...current.draft, examples: [...(current.draft.examples || []), { user: "", assistant: "" }] },
            }))}
          >
            <Plus size={15} /> 新增示例
          </button>
        </div>
        {(draft.examples || []).map((example, index) => (
          <div className="example-row" key={index}>
            <textarea placeholder="用户怎么问" value={example.user || ""} onChange={(e) => patchExample(index, "user", e.target.value)} />
            <textarea placeholder="机器人怎么答" value={example.assistant || ""} onChange={(e) => patchExample(index, "assistant", e.target.value)} />
          </div>
        ))}
      </div>
    </div>
  );
}

function BindingForm({ draft, config, patch }) {
  const selected = new Set(draft.knowledgeBaseIds || []);
  function toggleKb(kbId) {
    const next = new Set(selected);
    if (next.has(kbId)) next.delete(kbId);
    else next.add(kbId);
    patch("knowledgeBaseIds", Array.from(next));
  }

  return (
    <div className="form-grid">
      <Field label="微信群名"><input value={draft.group || ""} onChange={(e) => patch("group", e.target.value)} /></Field>
      <Field label="机器人">
        <select value={draft.botId || ""} onChange={(e) => patch("botId", e.target.value)}>
          <option value="">请选择机器人</option>
          {config.botProfiles.map((bot) => <option key={bot.id} value={bot.id}>{bot.name || bot.id}</option>)}
        </select>
      </Field>
      <div className="wide picker-panel">
        <strong>绑定知识库</strong>
        <div className="kb-picker">
          {config.knowledgeBases.map((kb) => (
            <button
              type="button"
              key={kb.id}
              className={classNames("kb-pill", selected.has(kb.id) && "selected")}
              onClick={() => toggleKb(kb.id)}
            >
              {kb.name || kb.id}
            </button>
          ))}
        </div>
      </div>
      <Field label="触发词，一行一个" wide>
        <textarea value={lines(draft.replyTriggers)} onChange={(e) => patch("replyTriggers", splitLines(e.target.value))} />
      </Field>
    </div>
  );
}

function GlobalForm({ draft, patch }) {
  return (
    <div className="form-grid">
      <Field label="冷却时间，秒">
        <input type="number" value={draft.cooldownSeconds ?? 30} onChange={(e) => patch("cooldownSeconds", Number(e.target.value))} />
      </Field>
      <label className="field switch-field">
        <span>智能提问检测</span>
        <input type="checkbox" checked={draft.smartDetection !== false} onChange={(e) => patch("smartDetection", e.target.checked)} />
      </label>
      <Field label="排除群，一行一个" wide>
        <textarea value={lines(draft.excludeGroups)} onChange={(e) => patch("excludeGroups", splitLines(e.target.value))} />
      </Field>
      <Field label="管理员微信名，一行一个" wide>
        <textarea value={lines(draft.admins)} onChange={(e) => patch("admins", splitLines(e.target.value))} />
      </Field>
    </div>
  );
}
