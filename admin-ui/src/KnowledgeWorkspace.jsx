import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Database,
  FileText,
  FileUp,
  FolderOpen,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Trash2,
  UploadCloud,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const ACCEPTED_FILES = ".doc,.docx,.wps,.ppt,.pptx,.xls,.xlsx,.md,.txt,.pdf,.epub,.mobi";
const BUSY_DOCUMENT_STATUSES = new Set(["PROCESSING", "UPDATING", "DELETING"]);

function classNames(...items) {
  return items.filter(Boolean).join(" ");
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

function formatTime(value) {
  if (!value) return "暂无记录";
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

function getKnowledgeState(item) {
  if (item?.provider === "maxkb") {
    if (item?.configured) {
      return { key: "ready", label: "已绑定", description: "MaxKB 应用已配置，可直接生成群聊回复。", icon: CheckCircle2 };
    }
    return { key: "draft", label: "未绑定", description: "请填写 MaxKB App ID。", icon: Clock3 };
  }
  const status = String(item?.indexStatus || "").toUpperCase();
  if (status === "FAILED") {
    return {
      key: "failed",
      label: "处理失败",
      description: "最近一次索引任务失败，需要检查文档后重试。",
      icon: AlertTriangle,
    };
  }
  if (status === "PENDING" || status === "RUNNING") {
    return {
      key: "processing",
      label: status === "PENDING" ? "索引任务已提交" : "正在构建索引",
      description: status === "PENDING"
        ? "文档已完成上传和解析，正在等待索引任务执行。"
        : "云端正在为文档构建检索索引。",
      icon: LoaderCircle,
    };
  }
  if (item?.configured) {
    return {
      key: "ready",
      label: "可用",
      description: "知识库已创建，可以参与群聊检索。",
      icon: CheckCircle2,
    };
  }
  return {
    key: "draft",
    label: "待上传",
    description: "上传第一批文档后会自动创建云知识库。",
    icon: Clock3,
  };
}

function documentStatusLabel(status) {
  return {
    PROCESSING: "处理中",
    ACTIVE: "有效",
    UPDATING: "更新中",
    DELETING: "删除中",
    DELETED: "已删除",
    FAILED: "失败",
    SUPERSEDED: "历史版本",
  }[status] || status || "未知";
}

function getBoundGroups(bindings, knowledgeBaseId) {
  return (bindings || []).filter((binding) =>
    (binding.knowledgeBaseIds || []).includes(knowledgeBaseId),
  );
}

function KnowledgeStatus({ knowledgeBase, compact = false }) {
  const state = getKnowledgeState(knowledgeBase);
  const Icon = state.icon;
  return (
    <span className={classNames("knowledge-status", `is-${state.key}`, compact && "is-compact")}>
      <Icon size={compact ? 13 : 15} className={state.key === "processing" ? "spin" : ""} />
      {state.label}
    </span>
  );
}

function KnowledgeList({
  items,
  bindings,
  query,
  onQueryChange,
  onCreate,
  onSelect,
  onRemove,
}) {
  return (
    <section className="content-panel config-only knowledge-workspace">
      <div className="panel-head knowledge-list-head">
        <div className="panel-title">
          <div className="title-icon amber">
            <Database size={19} />
          </div>
          <div>
            <h2>知识库</h2>
            <p>查看可用状态、文档规模和群绑定，再进入详情管理内容。</p>
          </div>
        </div>
        <div className="panel-tools">
          <label className="search-box">
            <Search size={16} />
            <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索名称、标签或 ID" />
          </label>
          <button type="button" className="primary-button slim" onClick={onCreate}>
            <Plus size={17} />
            新建知识库
          </button>
        </div>
      </div>

      {!items.length ? (
        <div className="empty-state knowledge-empty">
          <FolderOpen size={38} />
          <strong>{query ? "没有匹配的知识库" : "还没有知识库"}</strong>
          <span>{query ? "换一个关键词，或清空搜索条件。" : "新建后上传文档，系统会自动创建云知识库。"}</span>
        </div>
      ) : (
        <div className="knowledge-card-list">
          {items.map(({ item, index }) => {
            const state = getKnowledgeState(item);
            const groups = getBoundGroups(bindings, item.id);
            return (
              <article
                className="knowledge-card"
                key={item.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelect(item.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") onSelect(item.id);
                }}
              >
                <div className={classNames("knowledge-card-icon", `is-${state.key}`)}>
                  <Database size={23} />
                </div>
                <div className="knowledge-card-content">
                  <strong>{item.name || item.id}</strong>
                  <span>{item.description || "尚未填写知识库描述"}</span>
                </div>
                <div className="knowledge-card-facts">
                  <span><FileText size={14} /> {item.documentCount || 0} 份文档</span>
                  <span><UsersRound size={14} /> {groups.length} 个群</span>
                </div>
                <KnowledgeStatus knowledgeBase={item} />
                <div className="knowledge-card-actions" onClick={(event) => event.stopPropagation()}>
                  <button type="button" className="ghost-button slim" onClick={() => onSelect(item.id)}>
                    管理
                    <ChevronRight size={16} />
                  </button>
                  <button
                    type="button"
                    className="knowledge-remove-button"
                    aria-label={`删除配置 ${item.name || item.id}`}
                    onClick={() => onRemove(index)}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function getPipelineState({ selectedCount, uploadPhase, jobStatus }) {
  const status = String(jobStatus || "").toUpperCase();
  if (uploadPhase === "failed") {
    return {
      activeIndex: 1,
      doneThrough: 0,
      failed: true,
      labels: ["文件已选择", "处理失败", "索引任务已提交", "构建索引", "处理完成"],
    };
  }
  if (status === "FAILED") {
    return {
      activeIndex: 3,
      doneThrough: 2,
      failed: true,
      labels: ["文件已选择", "上传并解析完成", "索引任务已提交", "处理失败", "处理完成"],
    };
  }
  if (uploadPhase === "uploading") {
    return {
      activeIndex: 1,
      doneThrough: 0,
      labels: ["文件已选择", "上传并解析中", "索引任务已提交", "构建索引", "处理完成"],
    };
  }
  if (uploadPhase === "tracking") {
    if (status === "COMPLETED") {
      return {
        activeIndex: -1,
        doneThrough: 4,
        labels: ["文件已选择", "上传并解析完成", "索引任务已提交", "索引构建完成", "处理完成"],
      };
    }
    if (status === "RUNNING") {
      return {
        activeIndex: 3,
        doneThrough: 2,
        labels: ["文件已选择", "上传并解析完成", "索引任务已提交", "正在构建索引", "处理完成"],
      };
    }
    return {
      activeIndex: 2,
      doneThrough: 1,
      labels: ["文件已选择", "上传并解析完成", "索引任务已提交", "构建索引", "处理完成"],
    };
  }
  if (selectedCount > 0) {
    return {
      activeIndex: -1,
      doneThrough: 0,
      labels: ["文件已选择", "上传并解析", "索引任务已提交", "构建索引", "处理完成"],
    };
  }
  return {
    activeIndex: 0,
    doneThrough: -1,
    labels: ["尚未选择文件", "上传并解析", "索引任务已提交", "构建索引", "处理完成"],
  };
}

function PipelineStatus({ selectedCount, uploadPhase, jobStatus }) {
  const state = getPipelineState({ selectedCount, uploadPhase, jobStatus });
  return (
    <div className="knowledge-pipeline">
      {state.labels.map((step, index) => {
        const done = index <= state.doneThrough;
        const current = index === state.activeIndex;
        const failed = state.failed && current;
        return (
          <div
            className={classNames("pipeline-step", done && "is-done", current && "is-current", failed && "is-failed")}
            key={`${index}-${step}`}
          >
            <span>{done ? <CheckCircle2 size={13} /> : failed ? <AlertTriangle size={13} /> : index + 1}</span>
            <em>{step}</em>
          </div>
        );
      })}
    </div>
  );
}

function InlineUpload({
  knowledgeBase,
  uploading,
  selectedFiles,
  uploadPhase,
  jobStatus,
  uploadMessage,
  onFiles,
  onRemoveFile,
  onUpload,
  onClose,
}) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function acceptFiles(fileList) {
    const next = Array.from(fileList || []);
    if (next.length) onFiles(next);
  }

  return (
    <section className="knowledge-upload-panel">
      <div className="knowledge-upload-head">
        <div>
          <span>添加内容</span>
          <strong>{knowledgeBase.configured ? "向知识库追加文档" : "上传文档并创建知识库"}</strong>
          <p>支持 PDF、Office、WPS、Markdown、TXT 和电子书格式，单次最多上传平台允许的文件数量。</p>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="收起上传区域">
          <X size={18} />
        </button>
      </div>

      <PipelineStatus
        selectedCount={selectedFiles.length}
        uploadPhase={uploadPhase}
        jobStatus={jobStatus}
      />

      <button
        type="button"
        className={classNames("knowledge-dropzone", dragging && "is-dragging")}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          acceptFiles(event.dataTransfer.files);
        }}
      >
        <UploadCloud size={28} />
        <strong>拖拽文档到这里，或点击选择文件</strong>
        <span>文件上传后将由云端完成解析、切片和索引。</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        accept={ACCEPTED_FILES}
        onChange={(event) => {
          acceptFiles(event.target.files);
          event.target.value = "";
        }}
      />

      {selectedFiles.length > 0 && (
        <div className="knowledge-selected-files">
          {selectedFiles.map((file, index) => (
            <div key={`${file.name}-${file.size}-${index}`}>
              <FileText size={16} />
              <span>
                <strong>{file.name}</strong>
                <em>{formatSize(file.size)}</em>
              </span>
              <button type="button" onClick={() => onRemoveFile(index)} disabled={uploading} aria-label={`移除 ${file.name}`}>
                <X size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      {uploadMessage && (
        <div
          className={classNames(
            "knowledge-upload-message",
            uploading && "is-processing",
            uploadPhase === "failed" && "is-failed",
          )}
        >
          {uploadMessage}
        </div>
      )}

      <div className="knowledge-upload-actions">
        <span>{selectedFiles.length ? `已选择 ${selectedFiles.length} 个文件` : "尚未选择文件"}</span>
        <button type="button" className="primary-button" disabled={uploading || !selectedFiles.length} onClick={onUpload}>
          {uploading ? <LoaderCircle size={16} className="spin" /> : <FileUp size={16} />}
          {uploading ? "正在上传并解析..." : knowledgeBase.configured ? "上传并追加" : "上传并创建"}
        </button>
      </div>
    </section>
  );
}

function DocumentTable({
  documents,
  loading,
  error,
  onRefresh,
  onReplace,
  onDelete,
}) {
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(() => new Set());
  const [actionId, setActionId] = useState("");
  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return documents;
    return documents.filter((item) => item.name?.toLowerCase().includes(keyword));
  }, [documents, query]);

  function toggleVersion(documentId) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
  }

  return (
    <section className="knowledge-documents-panel">
      <div className="knowledge-table-toolbar">
        <label className="search-box">
          <Search size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索文档名称" />
        </label>
        <button type="button" className="ghost-button slim" disabled={loading} onClick={onRefresh}>
          <RefreshCw size={15} className={loading ? "spin" : ""} />
          {loading ? "同步中..." : "同步状态"}
        </button>
      </div>

      {error && <div className="document-error knowledge-table-error">{error}</div>}

      {!loading && !documents.length ? (
        <div className="knowledge-document-empty">
          <FileText size={36} />
          <strong>还没有文档</strong>
          <span>点击页面右上角“上传文档”，添加第一批可检索内容。</span>
        </div>
      ) : !filtered.length ? (
        <div className="knowledge-document-empty compact">
          <Search size={28} />
          <strong>没有匹配的文档</strong>
          <span>尝试缩短关键词或清空搜索。</span>
        </div>
      ) : (
        <div className="knowledge-document-table">
          <div className="knowledge-document-header">
            <span>序号</span>
            <span>文档</span>
            <span>状态</span>
            <span>版本</span>
            <span>更新时间</span>
            <span>操作</span>
          </div>
          {filtered.map((document, index) => {
            const busy = BUSY_DOCUMENT_STATUSES.has(document.status);
            const acting = actionId === document.id;
            const isExpanded = expanded.has(document.id);
            return (
              <div className="knowledge-document-record" key={document.id}>
                <div className="knowledge-document-row">
                  <span className="knowledge-document-index">{index + 1}</span>
                  <div className="knowledge-document-name">
                    <FileText size={18} />
                    <span>
                      <strong>{document.name}</strong>
                      <em>{formatSize(document.versions?.[0]?.sizeBytes || 0)}</em>
                    </span>
                  </div>
                  <span className={classNames("document-status", `status-${String(document.status || "").toLowerCase()}`)}>
                    {documentStatusLabel(document.status)}
                  </span>
                  <button type="button" className="version-toggle" onClick={() => toggleVersion(document.id)}>
                    v{document.currentVersion || "--"}
                    {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <span className="knowledge-document-time">{formatTime(document.updatedAt)}</span>
                  <div className="knowledge-document-actions">
                    <label className={classNames("ghost-button", "slim", (busy || acting || document.status === "DELETED") && "disabled")}>
                      <FileUp size={14} />
                      {acting ? "处理中" : "替换"}
                      <input
                        type="file"
                        hidden
                        accept={ACCEPTED_FILES}
                        disabled={busy || acting || document.status === "DELETED"}
                        onChange={(event) => {
                          const file = event.target.files?.[0];
                          event.target.value = "";
                          if (!file) return;
                          setActionId(document.id);
                          onReplace(document.id, file).finally(() => setActionId(""));
                        }}
                      />
                    </label>
                    <button
                      type="button"
                      className="document-delete-button"
                      disabled={busy || acting || document.status === "DELETED"}
                      onClick={() => {
                        if (!window.confirm(`确认删除“${document.name}”？删除后机器人将无法再检索这份文档。`)) return;
                        setActionId(document.id);
                        onDelete(document.id).finally(() => setActionId(""));
                      }}
                    >
                      <Trash2 size={14} />
                      删除
                    </button>
                  </div>
                </div>
                {isExpanded && (
                  <div className="knowledge-version-list">
                    {(document.versions || []).map((version) => (
                      <div key={`${document.id}-${version.version}`}>
                        <span>v{version.version}</span>
                        <strong>{version.fileName}</strong>
                        <span>{formatSize(version.sizeBytes)}</span>
                        <em>{documentStatusLabel(version.status)}</em>
                        <span>{formatTime(version.createdAt)}</span>
                        {version.error && <b>{version.error}</b>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function KnowledgeSettingsDrawer({ knowledgeBase, onClose, onSave }) {
  const [draft, setDraft] = useState(() => structuredClone(knowledgeBase));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(structuredClone(knowledgeBase));
    setError("");
  }, [knowledgeBase.id, knowledgeBase.provider]);

  function patch(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await onSave(knowledgeBase.id, draft);
      onClose();
    } catch (saveError) {
      setError(saveError.message || String(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="knowledge-settings-drawer" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <span>检索设置</span>
            <h2>知识库设置</h2>
            <p>调整名称、路由提示和未命中策略。云端标识由平台维护。</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭设置">
            <X size={19} />
          </button>
        </div>

        <div className="drawer-body">
          {error && <div className="modal-error">{error}</div>}
          <section className="settings-group">
            <div>
              <strong>基础信息</strong>
              <span>配置 MaxKB 应用连接和展示信息。</span>
            </div>
            <label className="field">
              <span>名称</span>
              <input value={draft.name || ""} onChange={(event) => patch("name", event.target.value)} />
            </label>
            <label className="field">
              <span>ID</span>
              <input
                value={draft.id || ""}
                readOnly={Boolean(knowledgeBase.configured)}
                onChange={(event) => patch("id", event.target.value)}
              />
              {knowledgeBase.configured && <em>知识库创建后 ID 不可修改。</em>}
            </label>
            <label className="field">
              <span>描述</span>
              <textarea value={draft.description || ""} onChange={(event) => patch("description", event.target.value)} />
            </label>
            <label className="field">
              <span>MaxKB App ID</span>
              <input value={draft.maxkbAppId || ""} onChange={(event) => patch("maxkbAppId", event.target.value)} placeholder="MaxKB 控制台 → 应用详情 → 复制应用 ID" />
            </label>
          </section>
        </div>

        <div className="drawer-foot">
          <span>保存后还需点击左侧“保存配置”写入本地。</span>
          <div>
            <button type="button" className="ghost-button" onClick={onClose}>取消</button>
            <button type="button" className="primary-button" disabled={saving} onClick={handleSave}>
              {saving ? "校验中..." : "保存设置"}
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

function KnowledgeDetail({
  knowledgeBase,
  bindings,
  onBack,
  onSaveDraft,
  onProvision,
  onRefreshJob,
  onListDocuments,
  onReplaceDocument,
  onDeleteDocument,
  onNavigateBindings,
}) {
  const [activeTab, setActiveTab] = useState("documents");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadPhase, setUploadPhase] = useState("idle");
  const [uploadJobStatus, setUploadJobStatus] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const boundGroups = getBoundGroups(bindings, knowledgeBase.id);

  async function loadDocuments(options = {}) {
    const { job = false, quiet = false } = options;
    if (!quiet) setLoading(true);
    setError("");
    try {
      const response = job && knowledgeBase.canRefreshStatus
        ? await onRefreshJob(knowledgeBase.id)
        : await onListDocuments(knowledgeBase.id);
      setDocuments(response.documentRecords || response.documents || []);
      if (response.status) {
        setUploadJobStatus(String(response.status).toUpperCase());
        setUploadPhase("tracking");
      }
    } catch (loadError) {
      setError(loadError.message || String(loadError));
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => {
    if (knowledgeBase.provider === "maxkb") {
      setDocuments([]);
      return;
    }
    if (!knowledgeBase.configured && !knowledgeBase.canRefreshStatus && !knowledgeBase.documentCount) {
      setDocuments([]);
      return;
    }
    loadDocuments();
  }, [knowledgeBase.id]);

  const hasBusyDocuments = documents.some((document) => BUSY_DOCUMENT_STATUSES.has(document.status));
  const knowledgeState = getKnowledgeState(knowledgeBase);
  useEffect(() => {
    if (!hasBusyDocuments && knowledgeState.key !== "processing") return undefined;
    const timer = window.setInterval(() => {
      loadDocuments({ job: true, quiet: true });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [knowledgeBase.id, knowledgeBase.canRefreshStatus, knowledgeState.key, hasBusyDocuments]);

  async function handleUpload() {
    if (!selectedFiles.length) return;
    setUploading(true);
    setUploadPhase("uploading");
    setUploadJobStatus("");
    setUploadMessage("正在上传并解析文档，请保持页面打开。");
    try {
      const response = await onProvision(knowledgeBase, selectedFiles);
      setSelectedFiles([]);
      setUploadJobStatus(String(response.knowledgeBase?.indexStatus || "PENDING").toUpperCase());
      setUploadPhase("tracking");
      setUploadMessage("索引任务已提交，系统会自动同步构建状态。");
      await loadDocuments({ job: true });
    } catch (uploadError) {
      setUploadPhase("failed");
      setUploadJobStatus("");
      setUploadMessage(uploadError.message || String(uploadError));
    } finally {
      setUploading(false);
    }
  }

  async function handleReplace(documentId, file) {
    setError("");
    try {
      await onReplaceDocument(knowledgeBase.id, documentId, file);
      await loadDocuments();
    } catch (replaceError) {
      setError(replaceError.message || String(replaceError));
    }
  }

  async function handleDelete(documentId) {
    setError("");
    try {
      await onDeleteDocument(knowledgeBase.id, documentId);
      await loadDocuments();
    } catch (deleteError) {
      setError(deleteError.message || String(deleteError));
    }
  }

  const latestUpdatedAt = documents
    .map((document) => document.updatedAt)
    .filter(Boolean)
    .sort()
    .at(-1);

  return (
    <section className="content-panel config-only knowledge-detail-page">
      <div className="knowledge-detail-head">
        <button type="button" className="knowledge-back-button" onClick={onBack}>
          <ArrowLeft size={18} />
          返回知识库
        </button>
        <div className="knowledge-detail-actions">
          <button type="button" className="ghost-button slim" onClick={() => setSettingsOpen(true)}>
            <Settings2 size={16} />
            知识库设置
          </button>
          {knowledgeBase.provider !== "maxkb" && (
            <button type="button" className="primary-button slim" onClick={() => {
              setActiveTab("documents");
              const currentStatus = String(knowledgeBase.indexStatus || "").toUpperCase();
              setUploadJobStatus(currentStatus);
              setUploadPhase(
                currentStatus === "PENDING" || currentStatus === "RUNNING"
                  ? "tracking"
                  : "idle",
              );
              setUploadMessage("");
              setUploadOpen(true);
            }}>
              <UploadCloud size={16} />
              上传文档
            </button>
          )}
        </div>
      </div>

      <div className="knowledge-detail-summary-nav">
        <div className="knowledge-detail-hero">
          <div className={classNames("knowledge-hero-icon", `is-${knowledgeState.key}`)}>
            <Database size={29} />
          </div>
          <div className="knowledge-hero-copy">
            <div>
              <h2>{knowledgeBase.name || knowledgeBase.id}</h2>
              <KnowledgeStatus knowledgeBase={knowledgeBase} />
            </div>
            <p>{knowledgeBase.description || "尚未填写知识库描述"}</p>
          </div>
          <nav className="knowledge-tabs" aria-label="知识库详情导航">
            {[
              ["documents", "文档管理", FileText],
              ["retrieval", "检索设置", Settings2],
            ].map(([key, label, Icon]) => (
              <button type="button" className={activeTab === key ? "is-active" : ""} key={key} onClick={() => setActiveTab(key)}>
                <Icon size={16} />
                {label}
                {key === "documents" && <em>{knowledgeBase.documentCount || documents.length || 0}</em>}
              </button>
            ))}
          </nav>
          <div className="knowledge-hero-facts">
            <button type="button" onClick={onNavigateBindings} title="前往全局群绑定管理">
              <UsersRound size={17} />
              <span>绑定群</span>
              <strong>{boundGroups.length}</strong>
              <ChevronRight size={14} className="knowledge-hero-fact-arrow" />
            </button>
            <div><Clock3 size={17} /><span>最近更新</span><strong>{formatTime(latestUpdatedAt)}</strong></div>
          </div>
        </div>
      </div>

      {activeTab === "documents" && (
        <div className="knowledge-detail-content">
          {knowledgeBase.provider === "maxkb" ? (
            <section className="knowledge-documents-panel">
              <div className="knowledge-document-empty">
                <Database size={36} />
                <strong>文档由 MaxKB 托管</strong>
                <span>请在 MaxKB 控制台维护知识库、应用提示词和云端模型；本项目只保存 App ID 并调用应用回答。</span>
              </div>
            </section>
          ) : (
            <DocumentTable
              documents={documents}
              loading={loading}
              error={error}
              onRefresh={() => loadDocuments({ job: true })}
              onReplace={handleReplace}
              onDelete={handleDelete}
            />
          )}
        </div>
      )}

      {activeTab === "retrieval" && (
        <div className="knowledge-detail-content is-retrieval">
          <section className="knowledge-info-grid">
            <article>
              <span>未命中策略</span>
              <strong>{knowledgeBase.fallbackPolicy === "general" ? "允许通用经验回答" : "资料不足先追问"}</strong>
              <p>机器人没有检索到足够资料时执行的回答策略。</p>
            </article>
            <article>
              <span>路由优先级</span>
              <strong>{knowledgeBase.priority || 0}</strong>
              <p>多个知识库同时匹配时用于辅助排序。</p>
            </article>
            <article className="wide">
              <span>路由示例问题</span>
              {(knowledgeBase.routeExamples || []).length ? (
                <div className="knowledge-example-list">
                  {knowledgeBase.routeExamples.map((example) => <em key={example}>{example}</em>)}
                </div>
              ) : <p>尚未配置示例问题。</p>}
            </article>
          </section>
        </div>
      )}

      {uploadOpen && (
        <div
          className="knowledge-upload-modal-backdrop"
          role="presentation"
          onMouseDown={() => {
            if (!uploading) setUploadOpen(false);
          }}
        >
          <div
            className="knowledge-upload-modal"
            role="dialog"
            aria-modal="true"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <InlineUpload
              knowledgeBase={knowledgeBase}
              uploading={uploading}
              selectedFiles={selectedFiles}
              uploadPhase={uploadPhase}
              jobStatus={uploadJobStatus}
              uploadMessage={uploadMessage}
              onFiles={(files) => {
                setSelectedFiles((current) => [...current, ...files]);
                setUploadPhase("idle");
                setUploadJobStatus("");
                setUploadMessage("");
              }}
              onRemoveFile={(index) => setSelectedFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
              onUpload={handleUpload}
              onClose={() => {
                if (!uploading) setUploadOpen(false);
              }}
            />
          </div>
        </div>
      )}

      {settingsOpen && (
        <KnowledgeSettingsDrawer
          knowledgeBase={knowledgeBase}
          onClose={() => setSettingsOpen(false)}
          onSave={onSaveDraft}
        />
      )}
    </section>
  );
}

export default function KnowledgeWorkspace({
  items,
  knowledgeBases,
  bindings,
  query,
  selectedId,
  onQueryChange,
  onCreate,
  onSelect,
  onBack,
  onRemove,
  onSaveDraft,
  onProvision,
  onRefreshJob,
  onListDocuments,
  onReplaceDocument,
  onDeleteDocument,
  onNavigateBindings,
}) {
  const selected = knowledgeBases.find((item) => item.id === selectedId);
  if (selected) {
    return (
      <KnowledgeDetail
        knowledgeBase={selected}
        bindings={bindings}
        onBack={onBack}
        onSaveDraft={onSaveDraft}
        onProvision={onProvision}
        onRefreshJob={onRefreshJob}
        onListDocuments={onListDocuments}
        onReplaceDocument={onReplaceDocument}
        onDeleteDocument={onDeleteDocument}
        onNavigateBindings={onNavigateBindings}
      />
    );
  }

  return (
    <KnowledgeList
      items={items}
      bindings={bindings}
      query={query}
      onQueryChange={onQueryChange}
      onCreate={onCreate}
      onSelect={onSelect}
      onRemove={onRemove}
    />
  );
}
