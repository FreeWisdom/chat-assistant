const state = {
  config: null,
  files: {},
  activeTab: "bots",
};

const content = document.getElementById("content");
const statusBox = document.getElementById("status");

function h(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setStatus(message, type = "") {
  statusBox.textContent = message;
  statusBox.className = `status ${type}`.trim();
}

async function requestJson(url, options = {}) {
  const resp = await fetch(url, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `请求失败: ${resp.status}`);
  }
  return data;
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

function getByPath(root, path) {
  return path.split(".").reduce((cur, part) => (cur == null ? undefined : cur[part]), root);
}

function setByPath(root, path, value) {
  const parts = path.split(".");
  let cur = root;
  for (let i = 0; i < parts.length - 1; i += 1) {
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = value;
}

function ensureConfigShape(config) {
  config.botProfiles ||= [];
  config.styles ||= [];
  config.knowledgeBases ||= [];
  config.bindings ||= [];
  config.global ||= {};
  config.global.excludeGroups ||= [];
  config.global.admins ||= [];
}

async function loadConfig() {
  setStatus("正在读取配置...");
  const data = await requestJson("/api/config");
  state.config = data.config;
  ensureConfigShape(state.config);
  await loadFiles();
  render();
  setStatus("配置已读取。", "ok");
}

async function loadFiles() {
  const data = await requestJson("/api/knowledge/files");
  state.files = data.files || {};
}

async function saveConfig() {
  setStatus("正在保存配置...");
  const data = await requestJson("/api/config", {
    method: "POST",
    body: JSON.stringify(state.config),
  });
  state.config = data.config;
  ensureConfigShape(state.config);
  await loadFiles();
  render();
  setStatus("配置已保存。重启 python main.py 后生效。", "ok");
}

async function validateConfig() {
  setStatus("正在校验配置...");
  const data = await requestJson("/api/validate", {
    method: "POST",
    body: JSON.stringify(state.config),
  });
  if (data.errors && data.errors.length) {
    setStatus(data.errors.join("\n"), "error");
  } else {
    setStatus("配置校验通过。", "ok");
  }
}

function styleOptions(selected) {
  return state.config.styles
    .map((style) => `<option value="${h(style.id)}" ${style.id === selected ? "selected" : ""}>${h(style.name || style.id)}</option>`)
    .join("");
}

function botOptions(selected) {
  return state.config.botProfiles
    .map((bot) => `<option value="${h(bot.id)}" ${bot.id === selected ? "selected" : ""}>${h(bot.name || bot.id)}</option>`)
    .join("");
}

function kbCheckboxes(binding, bindingIndex) {
  const selected = new Set(binding.knowledgeBaseIds || []);
  return state.config.knowledgeBases.map((kb) => `
    <label>
      <input type="checkbox" data-kb-check="${bindingIndex}" value="${h(kb.id)}" ${selected.has(kb.id) ? "checked" : ""}>
      ${h(kb.name || kb.id)}
    </label>
  `).join("");
}

function render() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === state.activeTab);
  });

  if (!state.config) {
    content.innerHTML = "";
    return;
  }

  const views = {
    bots: renderBots,
    styles: renderStyles,
    knowledge: renderKnowledge,
    bindings: renderBindings,
    global: renderGlobal,
  };
  content.innerHTML = views[state.activeTab]();
}

function renderBots() {
  const cards = state.config.botProfiles.map((bot, index) => `
    <article class="card">
      <div class="section-head">
        <h3>${h(bot.name || bot.id || "未命名机器人")}</h3>
        <button type="button" class="danger" data-action="remove-bot" data-index="${index}">删除</button>
      </div>
      <div class="form-grid">
        <label>ID<input data-path="botProfiles.${index}.id" value="${h(bot.id)}"></label>
        <label>名称<input data-path="botProfiles.${index}.name" value="${h(bot.name)}"></label>
        <label class="full">角色定位<input data-path="botProfiles.${index}.role" value="${h(bot.role)}"></label>
        <label>绑定风格<select data-path="botProfiles.${index}.styleId">${styleOptions(bot.styleId)}</select></label>
        <label>回答策略<input data-path="botProfiles.${index}.answerPolicyId" value="${h(bot.answerPolicyId || "strict-kb")}"></label>
        <label class="full">职责，一行一个<textarea data-path="botProfiles.${index}.responsibilities" data-list="true">${h(lines(bot.responsibilities))}</textarea></label>
        <label class="full">身份提示词<textarea data-path="botProfiles.${index}.identityPrompt">${h(bot.identityPrompt)}</textarea></label>
      </div>
    </article>
  `).join("");

  return `
    <div class="section-head">
      <h2>机器人身份</h2>
      <button type="button" class="primary" data-action="add-bot">新增机器人</button>
    </div>
    ${cards || `<p class="hint">还没有机器人身份。</p>`}
  `;
}

function renderStyles() {
  const cards = state.config.styles.map((style, index) => {
    const examples = (style.examples || []).map((example, exIndex) => `
      <div class="example">
        <label>用户示例<textarea data-path="styles.${index}.examples.${exIndex}.user">${h(example.user)}</textarea></label>
        <label>机器人回复<textarea data-path="styles.${index}.examples.${exIndex}.assistant">${h(example.assistant)}</textarea></label>
        <button type="button" class="danger" data-action="remove-example" data-index="${index}" data-example="${exIndex}">删除</button>
      </div>
    `).join("");

    return `
      <article class="card">
        <div class="section-head">
          <h3>${h(style.name || style.id || "未命名风格")}</h3>
          <button type="button" class="danger" data-action="remove-style" data-index="${index}">删除</button>
        </div>
        <div class="form-grid">
          <label>ID<input data-path="styles.${index}.id" value="${h(style.id)}"></label>
          <label>名称<input data-path="styles.${index}.name" value="${h(style.name)}"></label>
          <label class="full">语气<input data-path="styles.${index}.tone" value="${h(style.tone)}"></label>
          <label>最大字数<input type="number" min="1" data-path="styles.${index}.maxChars" data-number="true" value="${h(style.maxChars)}"></label>
          <label>表情策略<input data-path="styles.${index}.emojiPolicy" value="${h(style.emojiPolicy)}"></label>
          <label class="full">禁用表达，一行一个<textarea data-path="styles.${index}.avoidWords" data-list="true">${h(lines(style.avoidWords))}</textarea></label>
          <div class="full">
            <div class="section-head">
              <h3>风格示例</h3>
              <button type="button" data-action="add-example" data-index="${index}">新增示例</button>
            </div>
            ${examples || `<p class="hint">还没有风格示例。</p>`}
          </div>
        </div>
      </article>
    `;
  }).join("");

  return `
    <div class="section-head">
      <h2>回复风格</h2>
      <button type="button" class="primary" data-action="add-style">新增风格</button>
    </div>
    ${cards || `<p class="hint">还没有回复风格。</p>`}
  `;
}

function renderKnowledge() {
  const cards = state.config.knowledgeBases.map((kb, index) => {
    const files = (state.files[kb.id] || [])
      .map((file) => `<li>${h(file.name)} (${Math.ceil(file.size / 1024)} KB)</li>`)
      .join("");

    return `
      <article class="card">
        <div class="section-head">
          <h3>${h(kb.name || kb.id || "未命名知识库")}</h3>
          <button type="button" class="danger" data-action="remove-kb" data-index="${index}">删除</button>
        </div>
        <div class="form-grid">
          <label>ID<input data-path="knowledgeBases.${index}.id" value="${h(kb.id)}"></label>
          <label>名称<input data-path="knowledgeBases.${index}.name" value="${h(kb.name)}"></label>
          <label class="full">描述<input data-path="knowledgeBases.${index}.description" value="${h(kb.description)}"></label>
          <label>目录路径<input data-path="knowledgeBases.${index}.path" value="${h(kb.path)}"></label>
          <label>优先级<input type="number" data-path="knowledgeBases.${index}.priority" data-number="true" value="${h(kb.priority)}"></label>
          <label>未命中策略
            <select data-path="knowledgeBases.${index}.fallbackPolicy">
              <option value="clarify" ${kb.fallbackPolicy === "clarify" ? "selected" : ""}>先追问，不硬答</option>
              <option value="general" ${kb.fallbackPolicy === "general" ? "selected" : ""}>允许通用经验回答</option>
            </select>
          </label>
          <label class="full">标签，一行一个<textarea data-path="knowledgeBases.${index}.tags" data-list="true">${h(lines(kb.tags))}</textarea></label>
          <label class="full">路由示例问题，一行一个<textarea data-path="knowledgeBases.${index}.routeExamples" data-list="true">${h(lines(kb.routeExamples))}</textarea></label>
        </div>
        <div class="upload-box">
          <input type="file" data-upload-index="${index}" accept=".md,.txt,.json">
          <button type="button" data-action="upload-kb" data-index="${index}">上传到此知识库</button>
          <span class="hint">支持 .md / .txt / .json，保存到 ${h(kb.path)}</span>
        </div>
        <ul class="file-list">${files || `<li>暂无文件或未保存路径。</li>`}</ul>
      </article>
    `;
  }).join("");

  return `
    <div class="section-head">
      <h2>知识库</h2>
      <button type="button" class="primary" data-action="add-kb">新增知识库</button>
    </div>
    ${cards || `<p class="hint">还没有知识库。</p>`}
  `;
}

function renderBindings() {
  const cards = state.config.bindings.map((binding, index) => `
    <article class="card">
      <div class="section-head">
        <h3>${h(binding.group || "未命名群绑定")}</h3>
        <button type="button" class="danger" data-action="remove-binding" data-index="${index}">删除</button>
      </div>
      <div class="form-grid">
        <label>微信群名<input data-path="bindings.${index}.group" value="${h(binding.group)}"></label>
        <label>机器人<select data-path="bindings.${index}.botId">${botOptions(binding.botId)}</select></label>
        <div class="full">
          <label>绑定知识库</label>
          <div class="checkbox-list">${kbCheckboxes(binding, index) || `<span class="hint">请先新增知识库。</span>`}</div>
        </div>
        <label class="full">触发词，一行一个<textarea data-path="bindings.${index}.replyTriggers" data-list="true">${h(lines(binding.replyTriggers))}</textarea></label>
      </div>
    </article>
  `).join("");

  return `
    <div class="section-head">
      <h2>群绑定</h2>
      <button type="button" class="primary" data-action="add-binding">新增群绑定</button>
    </div>
    ${cards || `<p class="hint">还没有群绑定。</p>`}
  `;
}

function renderGlobal() {
  const globalCfg = state.config.global || {};
  return `
    <div class="section-head">
      <h2>全局设置</h2>
    </div>
    <article class="card">
      <div class="form-grid">
        <label>冷却时间，秒<input type="number" min="0" data-path="global.cooldownSeconds" data-number="true" value="${h(globalCfg.cooldownSeconds ?? 30)}"></label>
        <label class="checkbox-list">
          <input type="checkbox" data-path="global.smartDetection" data-bool="true" ${globalCfg.smartDetection !== false ? "checked" : ""}>
          开启智能提问检测
        </label>
        <label class="full">排除群，一行一个<textarea data-path="global.excludeGroups" data-list="true">${h(lines(globalCfg.excludeGroups))}</textarea></label>
        <label class="full">管理员微信名，一行一个<textarea data-path="global.admins" data-list="true">${h(lines(globalCfg.admins))}</textarea></label>
      </div>
    </article>
  `;
}

function addBot() {
  const id = `bot-${Date.now()}`;
  state.config.botProfiles.push({
    id,
    name: "新机器人",
    role: "",
    styleId: state.config.styles[0]?.id || "",
    answerPolicyId: "strict-kb",
    responsibilities: [],
    identityPrompt: "",
  });
}

function addStyle() {
  const id = `style-${Date.now()}`;
  state.config.styles.push({
    id,
    name: "新风格",
    tone: "像微信群里的熟人，简短直接",
    maxChars: 180,
    emojiPolicy: "少用",
    avoidWords: ["根据参考资料", "作为AI"],
    examples: [],
  });
}

function addKnowledgeBase() {
  const id = `kb-${Date.now()}`;
  state.config.knowledgeBases.push({
    id,
    name: "新知识库",
    description: "",
    path: `./knowledge/${id}`,
    tags: [],
    priority: 0,
    fallbackPolicy: "clarify",
    routeExamples: [],
  });
}

function addBinding() {
  state.config.bindings.push({
    group: "",
    botId: state.config.botProfiles[0]?.id || "",
    knowledgeBaseIds: state.config.knowledgeBases[0] ? [state.config.knowledgeBases[0].id] : [],
    replyTriggers: ["?", "？", "#举手"],
  });
}

async function uploadKnowledgeFile(index) {
  const kb = state.config.knowledgeBases[index];
  const input = document.querySelector(`[data-upload-index="${index}"]`);
  const file = input?.files?.[0];
  if (!kb?.id) {
    setStatus("请先填写知识库 ID。", "error");
    return;
  }
  if (!file) {
    setStatus("请先选择要上传的文件。", "error");
    return;
  }

  setStatus("正在上传知识库文件...");
  const form = new FormData();
  form.append("kb_id", kb.id);
  form.append("file", file);
  await requestJson("/api/knowledge/upload", {
    method: "POST",
    body: form,
  });
  await loadFiles();
  render();
  setStatus("知识库文件已上传。机器人重启后会重新加载知识库。", "ok");
}

document.querySelector(".tabs").addEventListener("click", (event) => {
  const tab = event.target.closest(".tab");
  if (!tab) return;
  state.activeTab = tab.dataset.tab;
  render();
});

content.addEventListener("input", (event) => {
  const target = event.target;
  if (!target.dataset.path) return;
  let value = target.value;
  if (target.dataset.list === "true") value = splitLines(value);
  if (target.dataset.number === "true") value = Number.parseInt(value || "0", 10);
  setByPath(state.config, target.dataset.path, value);
});

content.addEventListener("change", (event) => {
  const target = event.target;
  if (target.dataset.bool === "true") {
    setByPath(state.config, target.dataset.path, target.checked);
    return;
  }
  if (target.dataset.kbCheck) {
    const index = Number.parseInt(target.dataset.kbCheck, 10);
    const binding = state.config.bindings[index];
    const selected = new Set(binding.knowledgeBaseIds || []);
    if (target.checked) selected.add(target.value);
    else selected.delete(target.value);
    binding.knowledgeBaseIds = Array.from(selected);
    return;
  }
  if (target.dataset.path) {
    let value = target.value;
    if (target.dataset.number === "true") value = Number.parseInt(value || "0", 10);
    setByPath(state.config, target.dataset.path, value);
  }
});

content.addEventListener("click", async (event) => {
  const btn = event.target.closest("button[data-action]");
  if (!btn) return;

  const index = Number.parseInt(btn.dataset.index || "-1", 10);
  const example = Number.parseInt(btn.dataset.example || "-1", 10);

  try {
    switch (btn.dataset.action) {
      case "add-bot":
        addBot();
        break;
      case "remove-bot":
        state.config.botProfiles.splice(index, 1);
        break;
      case "add-style":
        addStyle();
        break;
      case "remove-style":
        state.config.styles.splice(index, 1);
        break;
      case "add-example":
        state.config.styles[index].examples ||= [];
        state.config.styles[index].examples.push({ user: "", assistant: "" });
        break;
      case "remove-example":
        state.config.styles[index].examples.splice(example, 1);
        break;
      case "add-kb":
        addKnowledgeBase();
        break;
      case "remove-kb":
        state.config.knowledgeBases.splice(index, 1);
        break;
      case "add-binding":
        addBinding();
        break;
      case "remove-binding":
        state.config.bindings.splice(index, 1);
        break;
      case "upload-kb":
        await uploadKnowledgeFile(index);
        return;
      default:
        break;
    }
    render();
  } catch (err) {
    setStatus(err.message, "error");
  }
});

document.getElementById("reloadBtn").addEventListener("click", () => {
  loadConfig().catch((err) => setStatus(err.message, "error"));
});

document.getElementById("saveBtn").addEventListener("click", () => {
  saveConfig().catch((err) => setStatus(err.message, "error"));
});

document.getElementById("validateBtn").addEventListener("click", () => {
  validateConfig().catch((err) => setStatus(err.message, "error"));
});

loadConfig().catch((err) => setStatus(err.message, "error"));
