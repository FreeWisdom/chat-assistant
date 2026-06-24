import {
  Activity,
  AlertTriangle,
  Bot,
  ChevronRight,
  CheckCircle2,
  Clock3,
  Database,
  FileClock,
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
  Trash2,
  UploadCloud,
  UsersRound,
  WandSparkles,
  Zap,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

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
    throw new Error(payload.detail || `请求失败：${response.status}`);
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

function providerLabel(provider) {
  return {
    aliyun_bailian: "阿里云百炼",
  }[provider || "aliyun_bailian"] || provider;
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
    workspaceId: "",
    indexId: "",
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
    if (!draft.workspaceId?.trim()) errors.push("阿里云百炼 Workspace ID 必填");
    if (!draft.indexId?.trim()) errors.push("阿里云百炼知识库 Index ID 必填");
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
  const [status, setStatus] = useState({ tone: "muted", text: "正在连接本地同步服务..." });
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    setStatus({ tone: "muted", text: "正在读取本地配置..." });
    const [configResponse, backupResponse] = await Promise.all([
      requestJson("/api/config"),
      requestJson("/api/backups"),
    ]);
    setConfig(ensureConfig(configResponse.config));
    setBackups(backupResponse.backups || []);
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

  async function restartScript() {
    setRestarting(true);
    setStatus({ tone: "muted", text: "正在重启机器人脚本..." });
    try {
      const response = await requestJson("/api/script/restart", { method: "POST" });
      const killedInfo = response.killed?.length ? `，已停掉旧进程 ${response.killed.length} 个` : "";
      setStatus({
        tone: "ok",
        text: `机器人脚本已启动${killedInfo}。日志：${response.log_file}`,
      });
    } finally {
      setRestarting(false);
    }
  }

  function patchGlobal(field, value) {
    setConfig((current) => ({
      ...current,
      global: { ...current.global, [field]: value },
    }));
    setStatus({ tone: "muted", text: "已更新页面配置，点击保存到脚本配置后写入本地。" });
  }

  function openModal(type, index = null) {
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
    openModalFromDraft(type, arrays[type].length - 1, arrays[type].at(-1));
  }

  function openModalFromDraft(type, index, draft) {
    setModal({ type, index, draft: structuredClone(draft), error: "" });
  }

  function removeItem(type, index) {
    const confirmed = window.confirm("确认删除这条配置？删除后还需要保存才会写入本地。");
    if (!confirmed) return;
    const next = structuredClone(config);
    if (type === "bots") next.botProfiles.splice(index, 1);
    if (type === "styles") next.styles.splice(index, 1);
    if (type === "knowledge") next.knowledgeBases.splice(index, 1);
    if (type === "bindings") next.bindings.splice(index, 1);
    setConfig(next);
    setStatus({ tone: "muted", text: "已从页面移除，点击保存到脚本配置后写入本地。" });
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
    if (modal.type === "knowledge") next.knowledgeBases[modal.index] = modal.draft;
    if (modal.type === "bindings") next.bindings[modal.index] = modal.draft;
    setConfig(next);
    setModal(null);
    setStatus({ tone: "muted", text: "详情已通过校验并更新到页面，点击保存到脚本配置后写入本地。" });
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
                onClick={() => setActive(key)}
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
          <button
            type="button"
            className="side-restart-button"
            disabled={restarting || saving}
            title="停掉正在跑的 main.py 并启动新进程。日志写入 wxauto_logs/restart_TIMESTAMP.log"
            onClick={() => restartScript().catch(showError)}
          >
            <RefreshCw size={16} />
            {restarting ? "重启中..." : "重启脚本"}
          </button>
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
            onNavigate={setActive}
            onCreate={createFromHome}
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
    </div>
  );

  function showError(error) {
    setStatus({ tone: "error", text: error.message || String(error) });
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
  const kbWithSources = safeConfig.knowledgeBases.filter(
    (kb) =>
      (kb.provider || "aliyun_bailian") === "aliyun_bailian"
      && Boolean(kb.workspaceId)
      && Boolean(kb.indexId),
  ).length;

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
    .filter((kb) => !kb.workspaceId || !kb.indexId)
    .slice(0, 2)
    .forEach((kb) => warnings.push({
      title: `${kb.name || kb.id} 云端标识不完整`,
      detail: "进入知识库详情填写阿里云百炼 Workspace ID 和 Index ID。",
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

function HomePage({ stats, config, backups, onNavigate, onCreate }) {
  const model = useMemo(() => buildHomeModel(config, backups), [config, backups]);
  const quickActions = [
    { title: "新建机器人", desc: "定义身份、职责、回答边界", icon: Bot, action: () => onCreate("bots") },
    { title: "新建风格", desc: "配置像真人一样的口吻", icon: WandSparkles, action: () => onCreate("styles") },
    { title: "接入云知识库", desc: "配置百炼 Workspace 和 Index", icon: Database, action: () => onCreate("knowledge") },
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
              <span>同步服务</span>
              <strong>在线</strong>
              <em>FastAPI · 127.0.0.1:8000</em>
            </div>
            <div className="status-item">
              <span>配置缓存</span>
              <strong>本地写入</strong>
              <em>config/bot.yaml</em>
            </div>
            <div className="status-item">
              <span>知识来源</span>
              <strong>阿里云百炼</strong>
              <em>运行时通过 Retrieve API 检索</em>
            </div>
            <div className="status-item">
              <span>生效方式</span>
              <strong>需重启</strong>
              <em>页面保存不会热更新机器人进程</em>
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
  if (type === "knowledge") return <Database size={22} />;
  return <MessageCircle size={22} />;
}

function getTitle(type, item) {
  if (type === "bindings") return item.group || "未命名微信群";
  return item.name || item.id || "未命名配置";
}

function getSubtitle(type, item, config) {
  if (type === "bots") return item.role || "未填写角色定位";
  if (type === "styles") return item.tone || "未填写风格说明";
  if (type === "knowledge") {
    const provider = item.provider || "aliyun_bailian";
    const sourceText = item.workspaceId && item.indexId
      ? `${item.workspaceId} / ${item.indexId}`
      : "云端标识未配置完整";
    return `${item.description || "未填写描述"} · ${providerLabel(provider)} · ${sourceText}`;
  }
  if (type === "bindings") {
    const bot = config.botProfiles.find((profile) => profile.id === item.botId);
    return `机器人：${bot?.name || item.botId || "未绑定"}`;
  }
  return "";
}

function getChips(type, item, config) {
  if (type === "bots") return [item.id, `风格 ${item.styleId || "未绑定"}`].filter(Boolean);
  if (type === "styles") return [`${item.maxChars || 0} 字以内`, `${item.examples?.length || 0} 个示例`];
  if (type === "knowledge") return [item.id, providerLabel(item.provider), item.fallbackPolicy === "general" ? "可通用回答" : "未命中先追问", ...(item.tags || []).slice(0, 4)];
  if (type === "bindings") {
    return [
      ...(item.knowledgeBaseIds || []).map((kbId) => config.knowledgeBases.find((kb) => kb.id === kbId)?.name || kbId),
      `${item.replyTriggers?.length || 0} 个触发词`,
    ].slice(0, 5);
  }
  return [];
}

function DetailModal({ modal, config, setModal, onClose, onSave }) {
  const meta = sectionMeta[modal.type];
  const Icon = meta.icon;

  function patch(field, value) {
    setModal((current) => ({ ...current, draft: { ...current.draft, [field]: value } }));
  }

  function patchExample(index, field, value) {
    setModal((current) => {
      const examples = [...(current.draft.examples || [])];
      examples[index] = { ...examples[index], [field]: value };
      return { ...current, draft: { ...current.draft, examples } };
    });
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="detail-modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <div className={`modal-icon ${meta.accent}`}>
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
          {modal.type === "knowledge" && (
            <KnowledgeForm draft={modal.draft} patch={patch} />
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

function KnowledgeForm({ draft, patch }) {
  const provider = draft.provider || "aliyun_bailian";
  return (
    <div className="form-grid">
      <Field label="ID"><input value={draft.id || ""} onChange={(e) => patch("id", e.target.value)} /></Field>
      <Field label="名称"><input value={draft.name || ""} onChange={(e) => patch("name", e.target.value)} /></Field>
      <Field label="类型">
        <select value={provider} onChange={(e) => patch("provider", e.target.value)}>
          <option value="aliyun_bailian">阿里云百炼</option>
        </select>
      </Field>
      <Field label="优先级"><input type="number" value={draft.priority || 0} onChange={(e) => patch("priority", Number(e.target.value))} /></Field>
      <Field label="未命中策略">
        <select value={draft.fallbackPolicy || "clarify"} onChange={(e) => patch("fallbackPolicy", e.target.value)}>
          <option value="clarify">资料不足先追问</option>
          <option value="general">允许通用经验回答</option>
        </select>
      </Field>
      <Field label="Workspace ID" wide>
        <input value={draft.workspaceId || ""} onChange={(e) => patch("workspaceId", e.target.value)} placeholder="llm-xxxxxxxx" />
      </Field>
      <Field label="Index ID" wide>
        <input value={draft.indexId || ""} onChange={(e) => patch("indexId", e.target.value)} placeholder="阿里云百炼知识库 ID" />
      </Field>
      <Field label="描述" wide><input value={draft.description || ""} onChange={(e) => patch("description", e.target.value)} /></Field>
      <Field label="标签，一行一个" wide><textarea value={lines(draft.tags)} onChange={(e) => patch("tags", splitLines(e.target.value))} /></Field>
      <Field label="路由示例问题，一行一个" wide>
        <textarea value={lines(draft.routeExamples)} onChange={(e) => patch("routeExamples", splitLines(e.target.value))} />
      </Field>
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
