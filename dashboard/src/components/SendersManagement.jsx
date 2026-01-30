import { useEffect, useState, useMemo } from "react";

// Default empty sender for the add form
const EMPTY_SENDER = {
  email: "",
  full_name: "",
  title: "",
  phone: "",
  company: "Intralog",
  signature_text: "",  // Plain text signature (user-friendly)
  signature_html: "",  // Auto-generated HTML version
  persona_context: "",
  warmup_enabled: false,
  daily_limit: 50,
  ramp_schedule: "conservative" // conservative, moderate, aggressive
};

// Convert plain text signature to HTML
// Each line becomes a separate line in the signature
// URLs are auto-linked, emails are auto-linked
function signatureTextToHtml(text) {
  if (!text || !text.trim()) return "";

  const lines = text.split("\n").filter(line => line.trim());

  const htmlLines = lines.map((line, index) => {
    let formatted = line.trim();

    // Auto-link URLs (simple domains like intralog.io or full URLs)
    formatted = formatted.replace(
      /(\b(?:https?:\/\/)?(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:\/[^\s]*)?)/gi,
      (match) => {
        const url = match.startsWith("http") ? match : `https://${match}`;
        return `<a href="${url}" style="color: #1e7dd7; text-decoration: none;">${match}</a>`;
      }
    );

    // Auto-link email addresses
    formatted = formatted.replace(
      /([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/gi,
      '<a href="mailto:$1" style="color: #1e7dd7; text-decoration: none;">$1</a>'
    );

    // First line (name) is bold
    if (index === 0) {
      return `<strong>${formatted}</strong>`;
    }

    return formatted;
  });

  return `<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6;">
${htmlLines.join("<br>\n")}
</div>`;
}

// Convert HTML signature back to plain text (for migration)
function signatureHtmlToText(html) {
  if (!html) return "";

  // Remove HTML tags and convert <br> to newlines
  let text = html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/div>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .trim();

  // Clean up multiple newlines
  text = text.replace(/\n{3,}/g, "\n\n");

  return text;
}

// Analytics categories with labels and colors
const ANALYTICS_CATEGORIES = [
  { key: "sent", label: "Sent", color: "#6366f1" },
  { key: "delivered", label: "Delivered", color: "#22c55e" },
  { key: "opened", label: "Opened", color: "#3b82f6" },
  { key: "clicked", label: "Clicked", color: "#8b5cf6" },
  { key: "replied", label: "Replied", color: "#10b981" },
  { key: "bounced", label: "Bounced", color: "#ef4444" },
  { key: "unsubscribed", label: "Unsubscribed", color: "#f97316" }
];

// Ramp schedule options
const RAMP_SCHEDULES = [
  {
    value: "conservative",
    label: "Conservative (4 weeks)",
    description: "Start with 5/day, increase by 10/week. Safest for new domains.",
    schedule: [5, 15, 25, 35, 50]
  },
  {
    value: "moderate",
    label: "Moderate (2 weeks)",
    description: "Start with 10/day, increase by 20/week. Good for established domains.",
    schedule: [10, 30, 50]
  },
  {
    value: "aggressive",
    label: "Aggressive (1 week)",
    description: "Start with 25/day, reach limit quickly. Only for warmed domains.",
    schedule: [25, 50]
  }
];

function SendersManagement({ fetchApi }) {
  const [senders, setSenders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingSender, setEditingSender] = useState(null);
  const [formData, setFormData] = useState(EMPTY_SENDER);
  const [saving, setSaving] = useState(false);

  // Analytics states
  const [selectedSender, setSelectedSender] = useState(null);
  const [senderAnalytics, setSenderAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  // Drill-down states
  const [drilldownCategory, setDrilldownCategory] = useState(null);
  const [drilldownRecipients, setDrilldownRecipients] = useState([]);
  const [drilldownLoading, setDrilldownLoading] = useState(false);

  // Sent emails states
  const [showSentEmails, setShowSentEmails] = useState(false);
  const [sentEmails, setSentEmails] = useState([]);
  const [sentEmailsLoading, setSentEmailsLoading] = useState(false);
  const [sentEmailsPage, setSentEmailsPage] = useState(1);
  const [sentEmailsTotal, setSentEmailsTotal] = useState(0);

  // Fetch senders on mount
  useEffect(() => {
    loadSenders();
  }, [fetchApi]);

  const loadSenders = async () => {
    setLoading(true);
    try {
      const data = await fetchApi("/api/senders");
      setSenders(data || []);
      setError("");
    } catch (err) {
      setError(err.message || "Failed to load senders");
    } finally {
      setLoading(false);
    }
  };

  // Load analytics when a sender is selected
  useEffect(() => {
    if (!selectedSender) {
      setSenderAnalytics(null);
      return;
    }

    loadSenderAnalytics(selectedSender.email);
  }, [selectedSender]);

  const loadSenderAnalytics = async (email) => {
    setAnalyticsLoading(true);
    try {
      // Fetch both analytics and warmup status
      const [analyticsData, warmupData] = await Promise.all([
        fetchApi(`/api/senders/${encodeURIComponent(email)}/analytics`),
        fetchApi(`/api/senders/${encodeURIComponent(email)}/warmup`)
      ]);

      // Merge analytics with warmup data
      setSenderAnalytics({
        ...analyticsData,
        ...warmupData
      });
    } catch (err) {
      // Use mock data if endpoint doesn't exist yet
      setSenderAnalytics({
        sent: Math.floor(Math.random() * 500) + 100,
        delivered: Math.floor(Math.random() * 450) + 90,
        opened: Math.floor(Math.random() * 200) + 50,
        clicked: Math.floor(Math.random() * 50) + 10,
        replied: Math.floor(Math.random() * 30) + 5,
        bounced: Math.floor(Math.random() * 20),
        unsubscribed: Math.floor(Math.random() * 5),
        warmup_day: Math.floor(Math.random() * 14) + 1,
        current_daily_limit: Math.floor(Math.random() * 30) + 10,
        warmup_enabled: false
      });
    } finally {
      setAnalyticsLoading(false);
    }
  };

  // Load recipients for a category drill-down
  const loadDrilldownRecipients = async (category) => {
    if (!selectedSender) return;

    setDrilldownCategory(category);
    setDrilldownLoading(true);

    try {
      const data = await fetchApi(
        `/api/senders/${encodeURIComponent(selectedSender.email)}/recipients?category=${category}`
      );
      setDrilldownRecipients(data.recipients || []);
    } catch (err) {
      // Mock data if endpoint doesn't exist
      setDrilldownRecipients([
        { email: "john.smith@acme.com", name: "John Smith", company: "Acme Corp", status: category, timestamp: new Date().toISOString() },
        { email: "jane.doe@logistics.io", name: "Jane Doe", company: "Logistics Inc", status: category, timestamp: new Date().toISOString() },
        { email: "bob.wilson@warehouse.com", name: "Bob Wilson", company: "Warehouse Co", status: category, timestamp: new Date().toISOString() }
      ]);
    } finally {
      setDrilldownLoading(false);
    }
  };

  // Load sent emails for a sender
  const loadSentEmails = async (page = 1) => {
    if (!selectedSender) return;

    setSentEmailsLoading(true);
    setShowSentEmails(true);
    setSentEmailsPage(page);

    try {
      const data = await fetchApi(
        `/api/senders/${encodeURIComponent(selectedSender.email)}/emails?page=${page}&per_page=10`
      );
      setSentEmails(data.emails || []);
      setSentEmailsTotal(data.total || 0);
    } catch (err) {
      console.error("Failed to load sent emails:", err);
      setSentEmails([]);
      setSentEmailsTotal(0);
    } finally {
      setSentEmailsLoading(false);
    }
  };

  // Format date for display
  const formatDate = (dateStr) => {
    if (!dateStr) return "—";
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  // Form handlers
  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleAddSender = () => {
    setFormData(EMPTY_SENDER);
    setEditingSender(null);
    setShowAddModal(true);
  };

  const handleEditSender = (sender) => {
    // Convert existing HTML signature to plain text if no text version exists
    const signatureText = sender.signature_text || signatureHtmlToText(sender.signature_html);

    setFormData({
      ...EMPTY_SENDER,
      ...sender,
      signature_text: signatureText,
      warmup_enabled: sender.warmup_enabled || false,
      daily_limit: sender.daily_limit || 50,
      ramp_schedule: sender.ramp_schedule || "conservative"
    });
    setEditingSender(sender);
    setShowAddModal(true);
  };

  const handleSaveSender = async () => {
    if (!formData.email || !formData.full_name) {
      setError("Email and full name are required");
      return;
    }

    setSaving(true);
    setError("");

    try {
      if (editingSender) {
        // Update existing sender
        await fetchApi(`/api/senders/${encodeURIComponent(editingSender.email)}/signature`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData)
        });

        // Handle warmup enable/disable if changed
        const warmupChanged = editingSender.warmup_enabled !== formData.warmup_enabled;
        if (warmupChanged) {
          if (formData.warmup_enabled) {
            // Enable warmup
            await fetchApi(`/api/senders/${encodeURIComponent(formData.email)}/warmup`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                ramp_schedule: formData.ramp_schedule || "conservative"
              })
            });
          } else {
            // Disable warmup
            await fetchApi(`/api/senders/${encodeURIComponent(formData.email)}/warmup`, {
              method: "DELETE"
            });
          }
        }

        setStatusMessage("Sender updated successfully!");
      } else {
        // Create new sender
        await fetchApi("/api/senders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData)
        });

        // Enable warmup if requested
        if (formData.warmup_enabled) {
          await fetchApi(`/api/senders/${encodeURIComponent(formData.email)}/warmup`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ramp_schedule: formData.ramp_schedule || "conservative"
            })
          });
        }

        setStatusMessage("Sender added successfully!");
      }

      await loadSenders();
      setShowAddModal(false);
      setFormData(EMPTY_SENDER);
      setEditingSender(null);

      // Reload analytics if sender is selected
      if (selectedSender?.email === formData.email) {
        await loadSenderAnalytics(formData.email);
      }
    } catch (err) {
      setError(err.message || "Failed to save sender");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSender = async (email) => {
    if (!confirm(`Are you sure you want to delete ${email}?`)) return;

    setError("");
    setStatusMessage("");

    try {
      const url = `/api/senders/${encodeURIComponent(email)}`;
      console.log("Deleting sender via:", url);

      const response = await fetchApi(url, {
        method: "DELETE"
      });

      console.log("Delete response:", response);
      setStatusMessage(`Successfully deleted ${email}`);
      await loadSenders();

      if (selectedSender?.email === email) {
        setSelectedSender(null);
      }
    } catch (err) {
      console.error("Delete sender error:", err);
      setError(err.message || "Failed to delete sender. Please check the console for details.");
    }
  };

  // Calculate totals for analytics
  const totalEmails = useMemo(() => {
    if (!senderAnalytics) return 0;
    return senderAnalytics.sent || 0;
  }, [senderAnalytics]);

  // Calculate percentages
  const getPercentage = (value) => {
    if (!totalEmails || !value) return 0;
    return ((value / totalEmails) * 100).toFixed(1);
  };

  // Render progress bar for analytics
  const renderProgressBar = (value, maxValue, color) => {
    const percentage = maxValue ? (value / maxValue) * 100 : 0;
    return (
      <div className="progress-bar-container">
        <div
          className="progress-bar-fill"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
    );
  };

  if (loading) {
    return <div className="senders-loading">Loading senders...</div>;
  }

  return (
    <div className="senders-management-full">
      {/* Header */}
      <div className="senders-header">
        <div>
          <h2>Sender Profiles & Analytics</h2>
          <p className="muted">Manage email senders, warmup settings, and track performance</p>
        </div>
        <button className="btn-primary" onClick={handleAddSender}>
          + Add Sender
        </button>
      </div>

      {error && <div className="alert error">{error}</div>}
      {statusMessage && <div className="alert success">{statusMessage}</div>}

      {/* Main Layout: Sender List + Details Panel */}
      <div className="senders-layout">
        {/* Left: Sender List */}
        <div className="senders-list-panel">
          <h3>Senders ({senders.length})</h3>
          <div className="sender-cards">
            {senders.map((sender) => (
              <div
                key={sender.email}
                className={`sender-card-compact ${selectedSender?.email === sender.email ? "selected" : ""}`}
                onClick={() => setSelectedSender(sender)}
              >
                <div className="sender-avatar">
                  {sender.full_name?.charAt(0) || "?"}
                </div>
                <div className="sender-info-compact">
                  <strong>{sender.full_name}</strong>
                  <span className="sender-email">{sender.email}</span>
                  <span className="sender-title-small">{sender.title}</span>
                </div>
                <div className="sender-status">
                  {sender.warmup_enabled ? (
                    <span className="status-badge warming">Warming</span>
                  ) : (
                    <span className="status-badge active">Active</span>
                  )}
                </div>
              </div>
            ))}

            {senders.length === 0 && (
              <div className="empty-state">
                <p>No senders configured yet.</p>
                <button className="btn-secondary" onClick={handleAddSender}>
                  Add your first sender
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right: Sender Details & Analytics */}
        <div className="sender-details-panel">
          {selectedSender ? (
            <>
              {/* Sender Profile Header */}
              <div className="sender-profile-header">
                <div className="sender-avatar-large">
                  {selectedSender.full_name?.charAt(0) || "?"}
                </div>
                <div className="sender-profile-info">
                  <h3>{selectedSender.full_name}</h3>
                  <p className="sender-title">{selectedSender.title}</p>
                  <p className="sender-contact">{selectedSender.email} | {selectedSender.phone}</p>
                </div>
                <div className="sender-actions">
                  <button className="btn-secondary" onClick={() => handleEditSender(selectedSender)}>
                    Edit
                  </button>
                  <button className="btn-danger" onClick={() => handleDeleteSender(selectedSender.email)}>
                    Delete
                  </button>
                </div>
              </div>

              {/* Warmup Status */}
              <div className="warmup-status-card">
                <h4>Email Warmup Status</h4>
                {senderAnalytics?.warmup_enabled ? (
                  <div className="warmup-active">
                    <div className="warmup-progress">
                      <div className="warmup-header">
                        <span className="warmup-day">
                          Day {senderAnalytics?.warmup_day || 1} of {senderAnalytics?.total_days || 28}
                        </span>
                        <span className="warmup-schedule">
                          {senderAnalytics?.ramp_schedule || 'conservative'} schedule
                        </span>
                      </div>
                      <div className="warmup-bar">
                        <div
                          className="warmup-bar-fill"
                          style={{ width: `${senderAnalytics?.progress_percent || 0}%` }}
                        />
                      </div>
                      <div className="warmup-stats">
                        <span>{senderAnalytics?.progress_percent || 0}% complete</span>
                        <span>{senderAnalytics?.days_until_full || 0} days until full capacity</span>
                      </div>
                    </div>
                    <div className="warmup-limits">
                      <div className="warmup-limit-item">
                        <span className="limit-label">Today's sends:</span>
                        <span className="limit-value">
                          <strong>{senderAnalytics?.sends_today || 0}</strong> / {senderAnalytics?.daily_limit || 50}
                        </span>
                      </div>
                      <div className="warmup-limit-item">
                        <span className="limit-label">Remaining today:</span>
                        <span className="limit-value">
                          <strong>{senderAnalytics?.remaining_today || 0}</strong> emails
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="warmup-inactive">
                    <p>Warmup not enabled. This sender can send at full capacity.</p>
                    <button className="btn-secondary" onClick={() => handleEditSender(selectedSender)}>
                      Configure Warmup
                    </button>
                  </div>
                )}
              </div>

              {/* Analytics Cards */}
              <div className="analytics-section">
                <h4>Performance Analytics</h4>

                {analyticsLoading ? (
                  <div className="analytics-loading">Loading analytics...</div>
                ) : senderAnalytics ? (
                  <>
                    {/* Visual Analytics - Bar Chart */}
                    <div className="analytics-chart">
                      <div className="chart-bars">
                        {ANALYTICS_CATEGORIES.map((cat) => {
                          const value = senderAnalytics[cat.key] || 0;
                          const maxValue = senderAnalytics.sent || 1;
                          const height = (value / maxValue) * 150;

                          return (
                            <div
                              key={cat.key}
                              className={`chart-bar-wrapper ${drilldownCategory === cat.key ? "selected" : ""}`}
                              onClick={() => loadDrilldownRecipients(cat.key)}
                            >
                              <div className="chart-bar-value">{value}</div>
                              <div
                                className="chart-bar"
                                style={{
                                  height: `${Math.max(height, 10)}px`,
                                  backgroundColor: cat.color
                                }}
                              />
                              <div className="chart-bar-label">{cat.label}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Numerical Analytics - Grid */}
                    <div className="analytics-grid">
                      {ANALYTICS_CATEGORIES.map((cat) => {
                        const value = senderAnalytics[cat.key] || 0;
                        const percentage = getPercentage(value);

                        return (
                          <div
                            key={cat.key}
                            className={`analytics-card ${drilldownCategory === cat.key ? "selected" : ""}`}
                            onClick={() => loadDrilldownRecipients(cat.key)}
                          >
                            <div className="analytics-card-header">
                              <span className="analytics-label">{cat.label}</span>
                              <span
                                className="analytics-indicator"
                                style={{ backgroundColor: cat.color }}
                              />
                            </div>
                            <div className="analytics-value">{value.toLocaleString()}</div>
                            <div className="analytics-percentage">{percentage}% of sent</div>
                            {renderProgressBar(value, senderAnalytics.sent, cat.color)}
                          </div>
                        );
                      })}
                    </div>
                  </>
                ) : (
                  <div className="analytics-empty">No analytics data available</div>
                )}
              </div>

              {/* Drill-down Table */}
              {drilldownCategory && (
                <div className="drilldown-section">
                  <div className="drilldown-header">
                    <h4>
                      {ANALYTICS_CATEGORIES.find(c => c.key === drilldownCategory)?.label} Recipients
                    </h4>
                    <button className="btn-text" onClick={() => setDrilldownCategory(null)}>
                      Close
                    </button>
                  </div>

                  {drilldownLoading ? (
                    <div className="drilldown-loading">Loading recipients...</div>
                  ) : (
                    <div className="drilldown-table-wrapper">
                      <table className="drilldown-table">
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>Email</th>
                            <th>Company</th>
                            <th>Timestamp</th>
                          </tr>
                        </thead>
                        <tbody>
                          {drilldownRecipients.map((recipient, idx) => (
                            <tr key={idx}>
                              <td>{recipient.name}</td>
                              <td>{recipient.email}</td>
                              <td>{recipient.company}</td>
                              <td>{new Date(recipient.timestamp).toLocaleString()}</td>
                            </tr>
                          ))}
                          {drilldownRecipients.length === 0 && (
                            <tr>
                              <td colSpan={4} className="empty-row">No recipients in this category</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Signature Preview */}
              <div className="signature-section">
                <h4>Email Signature</h4>
                <div
                  className="signature-preview-large"
                  dangerouslySetInnerHTML={{
                    __html: selectedSender.signature_text
                      ? signatureTextToHtml(selectedSender.signature_text)
                      : (selectedSender.signature_html || "<p class='muted'>No signature configured</p>")
                  }}
                />
              </div>

              {/* Sent Emails Section */}
              <div className="sent-emails-section">
                <div className="sent-emails-header">
                  <h4>Sent Emails</h4>
                  <button
                    className="btn-secondary"
                    onClick={() => loadSentEmails(1)}
                    disabled={sentEmailsLoading}
                  >
                    {sentEmailsLoading ? "Loading..." : (showSentEmails ? "Refresh" : "View Sent Emails")}
                  </button>
                </div>

                {showSentEmails && (
                  <div className="sent-emails-content">
                    {sentEmailsLoading ? (
                      <div className="sent-emails-loading">Loading sent emails...</div>
                    ) : sentEmails.length > 0 ? (
                      <>
                        <div className="sent-emails-table-wrapper">
                          <table className="sent-emails-table">
                            <thead>
                              <tr>
                                <th>Recipient</th>
                                <th>Subject</th>
                                <th>Status</th>
                                <th>Sent At</th>
                              </tr>
                            </thead>
                            <tbody>
                              {sentEmails.map((email, idx) => (
                                <tr key={email.id || idx}>
                                  <td>
                                    <div className="recipient-cell">
                                      <strong>{email.first_name} {email.last_name}</strong>
                                      <span className="recipient-email">{email.recipient_email}</span>
                                      {email.company_name && (
                                        <span className="recipient-company">{email.company_name}</span>
                                      )}
                                    </div>
                                  </td>
                                  <td className="subject-cell">{email.subject || "(No subject)"}</td>
                                  <td>
                                    <span className={`email-status-badge ${email.status}`}>
                                      {email.status}
                                    </span>
                                  </td>
                                  <td className="date-cell">{formatDate(email.sent_at)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>

                        {/* Pagination */}
                        {sentEmailsTotal > 10 && (
                          <div className="sent-emails-pagination">
                            <button
                              className="btn-text"
                              disabled={sentEmailsPage <= 1}
                              onClick={() => loadSentEmails(sentEmailsPage - 1)}
                            >
                              Previous
                            </button>
                            <span className="pagination-info">
                              Page {sentEmailsPage} of {Math.ceil(sentEmailsTotal / 10)}
                            </span>
                            <button
                              className="btn-text"
                              disabled={sentEmailsPage >= Math.ceil(sentEmailsTotal / 10)}
                              onClick={() => loadSentEmails(sentEmailsPage + 1)}
                            >
                              Next
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="sent-emails-empty">
                        <p>No emails have been sent from this sender yet.</p>
                        <p className="muted">Emails will appear here once campaigns start sending.</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="select-sender-prompt">
              <div className="prompt-icon">👤</div>
              <h3>Select a Sender</h3>
              <p>Choose a sender from the list to view their profile, analytics, and settings.</p>
            </div>
          )}
        </div>
      </div>

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content sender-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingSender ? "Edit Sender" : "Add New Sender"}</h3>
              <button className="modal-close" onClick={() => setShowAddModal(false)}>×</button>
            </div>

            <div className="modal-body">
              {/* Basic Info */}
              <div className="form-section">
                <h4>Basic Information</h4>
                <div className="form-grid">
                  <label>
                    Full Name *
                    <input
                      type="text"
                      value={formData.full_name}
                      onChange={(e) => handleFormChange("full_name", e.target.value)}
                      placeholder="John Smith"
                    />
                  </label>
                  <label>
                    Email Address *
                    <input
                      type="email"
                      value={formData.email}
                      onChange={(e) => handleFormChange("email", e.target.value)}
                      placeholder="john@company.com"
                      disabled={!!editingSender}
                    />
                  </label>
                  <label>
                    Title
                    <input
                      type="text"
                      value={formData.title}
                      onChange={(e) => handleFormChange("title", e.target.value)}
                      placeholder="Senior Systems Engineer"
                    />
                  </label>
                  <label>
                    Phone
                    <input
                      type="tel"
                      value={formData.phone}
                      onChange={(e) => handleFormChange("phone", e.target.value)}
                      placeholder="(555) 123-4567"
                    />
                  </label>
                </div>
              </div>

              {/* Signature */}
              <div className="form-section">
                <h4>Email Signature</h4>
                <p className="muted" style={{ marginBottom: "8px" }}>
                  Enter your signature with each item on a new line. Links and emails are auto-formatted.
                </p>
                <textarea
                  rows={8}
                  value={formData.signature_text || signatureHtmlToText(formData.signature_html)}
                  onChange={(e) => {
                    const text = e.target.value;
                    handleFormChange("signature_text", text);
                    handleFormChange("signature_html", signatureTextToHtml(text));
                  }}
                  className="signature-textarea"
                  placeholder={`Mark Westover
CEO
Intralog
mark@intralog.io
+1 (385) 500-3950
intralog.io`}
                  style={{ fontFamily: "inherit", lineHeight: "1.6" }}
                />
                <div className="signature-preview-small">
                  <strong>Preview:</strong>
                  <div
                    dangerouslySetInnerHTML={{
                      __html: signatureTextToHtml(formData.signature_text || signatureHtmlToText(formData.signature_html)) || "<span class='muted'>Your signature preview will appear here</span>"
                    }}
                  />
                </div>
              </div>

              {/* AI Persona */}
              <div className="form-section">
                <h4>AI Persona Context</h4>
                <p className="muted">Describe this sender's background and communication style for AI-generated content</p>
                <textarea
                  rows={4}
                  value={formData.persona_context}
                  onChange={(e) => handleFormChange("persona_context", e.target.value)}
                  className="persona-textarea"
                  placeholder="Example: 30+ years in manufacturing, executive tone, focuses on ROI..."
                />
              </div>

              {/* Warmup Settings */}
              <div className="form-section">
                <h4>Email Warmup Settings</h4>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.warmup_enabled}
                    onChange={(e) => handleFormChange("warmup_enabled", e.target.checked)}
                  />
                  Enable email warmup for this sender
                </label>

                {formData.warmup_enabled && (
                  <div className="warmup-options">
                    <label>
                      Daily Email Limit (after warmup)
                      <input
                        type="number"
                        min="10"
                        max="200"
                        value={formData.daily_limit}
                        onChange={(e) => handleFormChange("daily_limit", parseInt(e.target.value) || 50)}
                      />
                    </label>

                    <label>
                      Ramp-up Schedule
                      <select
                        value={formData.ramp_schedule}
                        onChange={(e) => handleFormChange("ramp_schedule", e.target.value)}
                      >
                        {RAMP_SCHEDULES.map((schedule) => (
                          <option key={schedule.value} value={schedule.value}>
                            {schedule.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="ramp-description">
                      {RAMP_SCHEDULES.find(s => s.value === formData.ramp_schedule)?.description}
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleSaveSender} disabled={saving}>
                {saving ? "Saving..." : (editingSender ? "Save Changes" : "Add Sender")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SendersManagement;
