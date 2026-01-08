import { useEffect, useMemo, useState } from "react";

const API_BASE_DEFAULT = import.meta.env.VITE_API_URL || "http://127.0.0.1:7000";
const TABS = ["Audience", "Content", "Emails", "Statistics", "Settings"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

async function fetchJson(baseUrl, path, options) {
  const response = await fetch(`${baseUrl}${path}`, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Request failed");
  }
  return response.json();
}

function formatNumber(value) {
  if (value === undefined || value === null) return "0";
  return value.toLocaleString();
}

function App() {
  const [campaigns, setCampaigns] = useState([]);
  const [activeId, setActiveId] = useState("");
  const [activeTab, setActiveTab] = useState("Audience");
  const [apiBase, setApiBase] = useState(
    () => window.localStorage.getItem("apiBase") || API_BASE_DEFAULT
  );
  const [apiStatus, setApiStatus] = useState("unknown");
  const [campaign, setCampaign] = useState(null);
  const [audience, setAudience] = useState({ rows: [], total: 0 });
  const [emails, setEmails] = useState({ rows: [], total: 0 });
  const [stats, setStats] = useState(null);
  const [senders, setSenders] = useState([]);
  const [contentDraft, setContentDraft] = useState(null);
  const [settingsDraft, setSettingsDraft] = useState(null);
  const [variantSelection, setVariantSelection] = useState({
    email_1: "variant_a",
    email_2: "variant_a"
  });
  const [newCampaignName, setNewCampaignName] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [generationDraft, setGenerationDraft] = useState({
    outputName: "",
    limit: ""
  });
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const normalizedApiBase = useMemo(() => apiBase.replace(/\/+$/, ""), [apiBase]);
  const fetchApi = (path, options) => fetchJson(normalizedApiBase, path, options);

  useEffect(() => {
    fetchApi("/api/campaigns")
      .then((data) => {
        setCampaigns(data);
        if (data.length > 0) {
          setActiveId(data[0].id);
        }
      })
      .catch((error) => setErrorMessage(error.message));
  }, [normalizedApiBase]);

  useEffect(() => {
    setApiStatus("checking");
    fetchApi("/api/health")
      .then(() => setApiStatus("connected"))
      .catch(() => setApiStatus("offline"));
  }, [apiBase]);

  useEffect(() => {
    if (!activeId) return;
    setErrorMessage("");
    fetchApi(`/api/campaigns/${activeId}`)
      .then((data) => {
        setCampaign(data);
        setContentDraft(data.sequence);
        setSettingsDraft(data.settings);
        setStats(data.stats);
      })
      .catch((error) => setErrorMessage(error.message));
  }, [activeId]);

  const deliveryBase = stats?.delivered || stats?.sent || 0;
  const scheduledBase = stats?.scheduled || 0;

  const ringData = [
    {
      label: "Sent",
      value: stats?.sent || 0,
      percent: scheduledBase ? (stats?.sent || 0) / scheduledBase * 100 : 0,
      color: "#1e7dd7",
      sublabel: scheduledBase ? `of ${formatNumber(scheduledBase)}` : "scheduled"
    },
    {
      label: "Opened",
      value: stats?.opened || 0,
      percent: deliveryBase ? (stats?.opened || 0) / deliveryBase * 100 : 0,
      color: "#1fa85a",
      sublabel: deliveryBase ? `${formatNumber(stats?.opened || 0)}` : "0"
    },
    {
      label: "Replied",
      value: stats?.replied || 0,
      percent: deliveryBase ? (stats?.replied || 0) / deliveryBase * 100 : 0,
      color: "#7d4df6",
      sublabel: deliveryBase ? `${formatNumber(stats?.replied || 0)}` : "0"
    },
    {
      label: "Successful",
      value: stats?.successful || 0,
      percent: deliveryBase ? (stats?.successful || 0) / deliveryBase * 100 : 0,
      color: "#18a780",
      sublabel: deliveryBase ? `${formatNumber(stats?.successful || 0)}` : "0"
    },
    {
      label: "Bounced",
      value: stats?.bounced || 0,
      percent: stats?.sent ? (stats?.bounced || 0) / stats.sent * 100 : 0,
      color: "#e08a2f",
      sublabel: stats?.sent ? `${formatNumber(stats?.bounced || 0)}` : "0"
    },
    {
      label: "Unsubscribed",
      value: stats?.unsubscribed || 0,
      percent: deliveryBase ? (stats?.unsubscribed || 0) / deliveryBase * 100 : 0,
      color: "#d14a4a",
      sublabel: deliveryBase ? `${formatNumber(stats?.unsubscribed || 0)}` : "0"
    }
  ];

  useEffect(() => {
    if (!activeId) return;
    if (activeTab === "Audience") {
      fetchApi(`/api/campaigns/${activeId}/audience?limit=200`)
        .then(setAudience)
        .catch((error) => setErrorMessage(error.message));
    }
    if (activeTab === "Emails") {
      fetchApi(`/api/campaigns/${activeId}/emails?limit=200`)
        .then(setEmails)
        .catch((error) => setErrorMessage(error.message));
    }
    if (activeTab === "Statistics") {
      fetchApi(`/api/campaigns/${activeId}/stats`)
        .then(setStats)
        .catch((error) => setErrorMessage(error.message));
    }
    if (activeTab === "Settings") {
      fetchApi("/api/senders")
        .then(setSenders)
        .catch((error) => setErrorMessage(error.message));
    }
  }, [activeId, activeTab]);

  const activeCampaignName = useMemo(() => {
    const active = campaigns.find((item) => item.id === activeId);
    return active ? active.name : "Campaign";
  }, [campaigns, activeId]);

  function updateContentDraft(emailKey, field, value) {
    setContentDraft((prev) => {
      if (!prev) return prev;
      const variantKey = variantSelection[emailKey];
      return {
        ...prev,
        [emailKey]: {
          ...prev[emailKey],
          [variantKey]: {
            ...prev[emailKey][variantKey],
            [field]: value
          }
        }
      };
    });
  }

  function handleSaveContent() {
    if (!contentDraft) return;
    setErrorMessage("");
    setStatusMessage("Saving content...");
    fetchApi(`/api/campaigns/${activeId}/content`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sequence: contentDraft })
    })
      .then(() => setStatusMessage("Content saved."))
      .catch((error) => {
        setStatusMessage("");
        setErrorMessage(error.message);
      });
  }

  function handleSaveSettings() {
    if (!settingsDraft) return;
    setErrorMessage("");
    setStatusMessage("Saving settings...");
    fetchApi(`/api/campaigns/${activeId}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: settingsDraft })
    })
      .then(() => setStatusMessage("Settings saved."))
      .catch((error) => {
        setStatusMessage("");
        setErrorMessage(error.message);
      });
  }

  function handleCreateCampaign() {
    const name = newCampaignName.trim();
    if (!name) {
      setErrorMessage("Campaign name is required.");
      return;
    }
    setErrorMessage("");
    setStatusMessage("Creating campaign...");
    fetchApi("/api/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, status: "draft" })
    })
      .then((created) => {
        setCampaigns((prev) => [...prev, created]);
        setActiveId(created.id);
        setNewCampaignName("");
        setStatusMessage("Campaign created.");
        setErrorMessage("");
      })
      .catch((error) => {
        setStatusMessage("");
        setErrorMessage(error.message);
      });
  }

  function handleUploadLeads() {
    if (!uploadFile) {
      setErrorMessage("Select a CSV file first.");
      return;
    }
    setErrorMessage("");
    setStatusMessage("Uploading leads...");
    const formData = new FormData();
    formData.append("file", uploadFile);
    fetch(`${normalizedApiBase}/api/campaigns/${activeId}/upload`, {
      method: "POST",
      body: formData
    })
      .then((response) => {
        if (!response.ok) {
          return response.text().then((text) => {
            throw new Error(text || "Upload failed");
          });
        }
        return response.json();
      })
      .then((updated) => {
        setCampaign(updated);
        setUploadFile(null);
        setStatusMessage("Leads uploaded.");
        return fetchApi(`/api/campaigns/${activeId}/audience?limit=200`);
      })
      .then(setAudience)
      .catch((error) => {
        setStatusMessage("");
        setErrorMessage(error.message);
      });
  }

  function handleGenerateCampaign() {
    setErrorMessage("");
    setStatusMessage("Generating output...");
    const payload = {
      output_name: generationDraft.outputName,
      limit: generationDraft.limit ? Number(generationDraft.limit) : null
    };
    fetchApi(`/api/campaigns/${activeId}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(() => fetchApi(`/api/campaigns/${activeId}`))
      .then((updated) => {
        setCampaign(updated);
        setStats(updated.stats);
        setStatusMessage("Output generated.");
        return fetchApi(`/api/campaigns/${activeId}/emails?limit=200`);
      })
      .then(setEmails)
      .catch((error) => {
        setStatusMessage("");
        setErrorMessage(error.message);
      });
  }


  function toggleSender(email) {
    setSettingsDraft((prev) => {
      if (!prev) return prev;
      const current = new Set(prev.sender_emails || []);
      if (current.has(email)) {
        current.delete(email);
      } else {
        current.add(email);
      }
      return { ...prev, sender_emails: Array.from(current) };
    });
  }

  function toggleDay(day) {
    setSettingsDraft((prev) => {
      if (!prev) return prev;
      const current = new Set((prev.schedule?.days || []));
      if (current.has(day)) {
        current.delete(day);
      } else {
        current.add(day);
      }
      return {
        ...prev,
        schedule: { ...(prev.schedule || {}), days: Array.from(current) }
      };
    });
  }

  function toggleTracking(field) {
    setSettingsDraft((prev) => {
      if (!prev) return prev;
      const tracking = prev.tracking || {};
      return {
        ...prev,
        tracking: { ...tracking, [field]: !tracking[field] }
      };
    });
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">PO</span>
          <div>
            <p className="brand-title">Campaign Studio</p>
            <p className="brand-subtitle">Personalized outreach ops</p>
          </div>
        </div>
        <div className="sidebar-section">
          <p className="sidebar-label">Campaigns</p>
          <div className="create-campaign">
            <div className="api-row">
              <input
                type="text"
                value={apiBase}
                onChange={(event) => setApiBase(event.target.value)}
                onBlur={(event) => {
                  const next = event.target.value.trim();
                  setApiBase(next);
                  window.localStorage.setItem("apiBase", next);
                }}
              />
              <span className={`api-status ${apiStatus}`}>{apiStatus}</span>
            </div>
            <input
              type="text"
              placeholder="Campaign name"
              value={newCampaignName}
              onChange={(event) => setNewCampaignName(event.target.value)}
            />
            <button className="primary-button small" onClick={handleCreateCampaign}>
              New campaign
            </button>
          </div>
          <div className="campaign-list">
            {campaigns.map((item) => (
              <button
                key={item.id}
                className={`campaign-pill ${item.id === activeId ? "active" : ""}`}
                onClick={() => setActiveId(item.id)}
              >
                <span>{item.name}</span>
                <span className="pill-status">{item.status}</span>
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="header">
          <div>
            <p className="eyebrow">Sequences</p>
            <h1>{activeCampaignName}</h1>
            <p className="subtitle">
              Personalization is the spine. Review structure, cadence, and engagement in one place.
            </p>
          </div>
          <div className="status-card">
            <div>
              <p className="status-label">Status</p>
              <p className="status-value">{campaign?.status || "draft"}</p>
            </div>
            <div className="status-stat">
              <span>Scheduled</span>
              <strong>{formatNumber(campaign?.stats?.scheduled || 0)}</strong>
            </div>
            <div className="status-stat">
              <span>Sent</span>
              <strong>{formatNumber(campaign?.stats?.sent || 0)}</strong>
            </div>
          </div>
        </header>

        <nav className="tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              className={`tab ${tab === activeTab ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </nav>

        {errorMessage && <div className="alert error">{errorMessage}</div>}
        {statusMessage && <div className="alert success">{statusMessage}</div>}

        <section className="tab-body">
          {activeTab === "Audience" && (
            <div className="panel">
              <div className="panel-header">
                <h2>Audience</h2>
                <span>{formatNumber(audience.total)} leads</span>
              </div>
              <div className="panel-meta">
                <span>Lead source: {campaign?.lead_source || "Not set"}</span>
                <span>Output: {campaign?.output_file || "Not generated"}</span>
              </div>
              <div className="upload-row">
                <input
                  type="file"
                  accept=".csv"
                  onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
                />
                <button className="primary-button small" onClick={handleUploadLeads}>
                  Upload leads
                </button>
              </div>
              <div className="table">
                <div className="table-row table-head">
                  <span>Name</span>
                  <span>Title</span>
                  <span>Company</span>
                  <span>Email</span>
                  <span>Industry</span>
                </div>
                {audience.rows.map((row, index) => (
                  <div className="table-row" key={`${row.email}-${index}`}>
                    <span>{row.name || "-"}</span>
                    <span>{row.title || "-"}</span>
                    <span>{row.company || "-"}</span>
                    <span>{row.email || "-"}</span>
                    <span>{row.industry || "-"}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "Content" && (
            <div className="content-grid">
              <div className="panel">
                <div className="panel-header">
                  <h2>Email 1 structure</h2>
                  <div className="variant-toggle">
                    {["variant_a", "variant_b"].map((variant) => (
                      <button
                        key={variant}
                        className={variantSelection.email_1 === variant ? "active" : ""}
                        onClick={() =>
                          setVariantSelection((prev) => ({ ...prev, email_1: variant }))
                        }
                      >
                        {variant === "variant_a" ? "Variant A" : "Variant B"}
                      </button>
                    ))}
                  </div>
                </div>
                <label>Subject</label>
                <input
                  type="text"
                  value={contentDraft?.email_1?.[variantSelection.email_1]?.subject || ""}
                  onChange={(event) =>
                    updateContentDraft("email_1", "subject", event.target.value)
                  }
                />
                <label>Body</label>
                <textarea
                  rows="10"
                  value={contentDraft?.email_1?.[variantSelection.email_1]?.body || ""}
                  onChange={(event) =>
                    updateContentDraft("email_1", "body", event.target.value)
                  }
                />
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>Email 2 structure</h2>
                  <div className="variant-toggle">
                    {["variant_a", "variant_b"].map((variant) => (
                      <button
                        key={variant}
                        className={variantSelection.email_2 === variant ? "active" : ""}
                        onClick={() =>
                          setVariantSelection((prev) => ({ ...prev, email_2: variant }))
                        }
                      >
                        {variant === "variant_a" ? "Variant A" : "Variant B"}
                      </button>
                    ))}
                  </div>
                </div>
                <label>Subject</label>
                <input
                  type="text"
                  value={contentDraft?.email_2?.[variantSelection.email_2]?.subject || ""}
                  onChange={(event) =>
                    updateContentDraft("email_2", "subject", event.target.value)
                  }
                />
                <label>Body</label>
                <textarea
                  rows="10"
                  value={contentDraft?.email_2?.[variantSelection.email_2]?.body || ""}
                  onChange={(event) =>
                    updateContentDraft("email_2", "body", event.target.value)
                  }
                />
                <button className="primary-button" onClick={handleSaveContent}>
                  Save variants
                </button>
              </div>

              <div className="panel panel-dark">
                <h3>Structure rules</h3>
                <ul>
                  <li>Greeting and personalization lead the message.</li>
                  <li>Credibility anchor stays equipment-only.</li>
                  <li>CTA is derived from the pain theme.</li>
                  <li>Follow-up narrows scope and raises certainty.</li>
                </ul>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>Generate output</h2>
                  <span>Use current templates</span>
                </div>
                <label>Output filename</label>
                <input
                  type="text"
                  value={generationDraft.outputName}
                  onChange={(event) =>
                    setGenerationDraft((prev) => ({
                      ...prev,
                      outputName: event.target.value
                    }))
                  }
                  placeholder="campaigns_equipment_first.csv"
                />
                <label>Limit (optional)</label>
                <input
                  type="number"
                  min="1"
                  value={generationDraft.limit}
                  onChange={(event) =>
                    setGenerationDraft((prev) => ({ ...prev, limit: event.target.value }))
                  }
                  placeholder="25"
                />
                <button className="primary-button" onClick={handleGenerateCampaign}>
                  Generate campaign
                </button>
              </div>
            </div>
          )}

          {activeTab === "Emails" && (
            <div className="panel">
              <div className="panel-header">
                <h2>Preview emails</h2>
                <span>{formatNumber(emails.total)} generated</span>
              </div>
              <div className="email-grid">
                {emails.rows.map((row, index) => (
                  <div className="email-card" key={`${row.recipient}-${index}`}>
                    <div className="email-meta">
                      <span>Seq {row.sequence}</span>
                      <span>{row.sender}</span>
                    </div>
                    <h4>{row.subject}</h4>
                    <pre>{row.body}</pre>
                    <p className="email-foot">
                      To: {row.recipient} | From: {row.sender_email}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "Statistics" && (
            <div className="stats-stack">
              <div className="panel stats-panel">
                <div className="panel-header">
                  <h2>Engagement</h2>
                  <span>Rates based on delivered unless noted</span>
                </div>
                <div className="stats-summary">
                  <div>
                    <p>Scheduled</p>
                    <strong>{formatNumber(stats?.scheduled || 0)}</strong>
                  </div>
                  <div>
                    <p>Sent</p>
                    <strong>{formatNumber(stats?.sent || 0)}</strong>
                  </div>
                  <div>
                    <p>Delivered</p>
                    <strong>{formatNumber(stats?.delivered || 0)}</strong>
                  </div>
                </div>
                <div className="ring-grid">
                  {ringData.map((item) => (
                    <div className="ring-card" key={item.label}>
                      <div
                        className="ring"
                        style={{
                          background: `conic-gradient(${item.color} ${item.percent}%, #e8eeec 0)`
                        }}
                      >
                        <div className="ring-core">
                          <div className="ring-value">
                            {item.label === "Sent"
                              ? formatNumber(item.value)
                              : `${item.percent.toFixed(1)}%`}
                          </div>
                          <div className="ring-sub">{item.sublabel}</div>
                        </div>
                      </div>
                      <span className="ring-label">{item.label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === "Settings" && (
            <div className="settings-grid">
              <div className="panel">
                <div className="panel-header">
                  <h2>Sender accounts</h2>
                  <span>Rotate across selected accounts</span>
                </div>
                <div className="table">
                  <div className="table-row table-head">
                    <span>Use</span>
                    <span>Account</span>
                    <span>Status</span>
                    <span>Sent today</span>
                    <span>Pending</span>
                  </div>
                  {senders.map((sender) => (
                    <div className="table-row" key={sender.email}>
                      <span>
                        <input
                          type="checkbox"
                          checked={settingsDraft?.sender_emails?.includes(sender.email) || false}
                          onChange={() => toggleSender(sender.email)}
                        />
                      </span>
                      <span>
                        <div className="sender-name">{sender.name}</div>
                        <div className="sender-email">{sender.email}</div>
                      </span>
                      <span className="status-pill">{sender.status}</span>
                      <span>{sender.sent_today}</span>
                      <span>{sender.pending}</span>
                    </div>
                  ))}
                </div>
                <div className="toggle-row">
                  <div>
                    <p className="toggle-title">On hold</p>
                    <p className="toggle-subtitle">Pause new sends for this campaign.</p>
                  </div>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={settingsDraft?.on_hold || false}
                      onChange={() =>
                        setSettingsDraft((prev) => {
                          const current = prev?.on_hold || false;
                          return { ...(prev || {}), on_hold: !current };
                        })
                      }
                    />
                    <span className="slider"></span>
                  </label>
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>Tracking</h2>
                  <span>Visibility for engagement</span>
                </div>
                <div className="toggle-row">
                  <div>
                    <p className="toggle-title">Track email opens</p>
                    <p className="toggle-subtitle">Track delivery opens in this sequence.</p>
                  </div>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={settingsDraft?.tracking?.opens || false}
                      onChange={() => toggleTracking("opens")}
                    />
                    <span className="slider"></span>
                  </label>
                </div>
                <div className="toggle-row">
                  <div>
                    <p className="toggle-title">Track link clicks</p>
                    <p className="toggle-subtitle">Only available when links are used.</p>
                  </div>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={settingsDraft?.tracking?.clicks || false}
                      onChange={() => toggleTracking("clicks")}
                    />
                    <span className="slider"></span>
                  </label>
                </div>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>Send window</h2>
                  <span>Schedule outbound windows</span>
                </div>
                <div className="settings-row">
                  <label>
                    Daily limit
                    <input
                      type="number"
                      min="1"
                      value={settingsDraft?.daily_limit ?? 40}
                      onChange={(event) =>
                        setSettingsDraft((prev) => ({
                          ...(prev || {}),
                          daily_limit: Number(event.target.value || 0)
                        }))
                      }
                    />
                  </label>
                  <label>
                    Follow-up delay (days)
                    <input
                      type="number"
                      min="0"
                      value={settingsDraft?.follow_up_delay_days ?? 4}
                      onChange={(event) =>
                        setSettingsDraft((prev) => ({
                          ...(prev || {}),
                          follow_up_delay_days: Number(event.target.value || 0)
                        }))
                      }
                    />
                  </label>
                </div>
                <div className="timezone-row">
                  <span>Send window timezone</span>
                  <strong>{settingsDraft?.schedule?.timezone || "MST (Mountain Standard Time)"}</strong>
                </div>
                <div className="day-grid">
                  {DAYS.map((day) => (
                    <button
                      key={day}
                      className={`day-pill ${
                        settingsDraft?.schedule?.days?.includes(day) ? "active" : ""
                      }`}
                      onClick={() => toggleDay(day)}
                    >
                      {day}
                    </button>
                  ))}
                </div>
                <div className="time-grid">
                  <label>
                    Start
                    <input
                      type="time"
                      value={settingsDraft?.schedule?.start_time || "09:00"}
                      onChange={(event) =>
                        setSettingsDraft((prev) => ({
                          ...(prev || {}),
                          schedule: { ...(prev?.schedule || {}), start_time: event.target.value }
                        }))
                      }
                    />
                  </label>
                  <label>
                    End
                    <input
                      type="time"
                      value={settingsDraft?.schedule?.end_time || "17:00"}
                      onChange={(event) =>
                        setSettingsDraft((prev) => ({
                          ...(prev || {}),
                          schedule: { ...(prev?.schedule || {}), end_time: event.target.value }
                        }))
                      }
                    />
                  </label>
                </div>
                <button className="primary-button" onClick={handleSaveSettings}>
                  Save settings
                </button>
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
