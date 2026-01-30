import { useEffect, useMemo, useState } from "react";
import VariableAutocomplete from "./VariableAutocomplete";
import EmailLivePreview from "./EmailLivePreview";

const STEP_TYPES = [
  { value: "email", label: "Email" },
  { value: "wait", label: "Wait" },
  { value: "call", label: "Call" },
  { value: "linkedin_connect", label: "LinkedIn connect" },
  { value: "linkedin_message", label: "LinkedIn message" }
];

const EMAIL_TEMPLATES = ["email_1", "email_2"];

const makeId = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `step-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function withUiIds(steps) {
  return (steps || []).map((step) => ({
    _uiId: makeId(),
    ...step
  }));
}

function stripUiIds(steps) {
  return (steps || []).map(({ _uiId, ...rest }) => rest);
}

function SequenceBuilder({ campaignId, fetchApi, variables }) {
  const [name, setName] = useState("");
  const [steps, setSteps] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [senders, setSenders] = useState([]);
  const [selectedSender, setSelectedSender] = useState("");
  const [personalizationMode, setPersonalizationMode] = useState("signal_based");
  const [includeSignature, setIncludeSignature] = useState(true);

  const totalDelay = useMemo(
    () => steps.reduce((acc, step) => acc + Number(step.delay_days || 0), 0),
    [steps]
  );

  // Fetch available senders
  useEffect(() => {
    fetchApi("/api/senders")
      .then((data) => {
        setSenders(data || []);
        // Set default sender to first one if not already set
        if (data && data.length > 0 && !selectedSender) {
          setSelectedSender(data[0].email);
        }
      })
      .catch(() => setSenders([]));
  }, [fetchApi]);

  useEffect(() => {
    if (!campaignId) return;
    let active = true;
    setLoading(true);
    setError("");
    setStatusMessage("");
    fetchApi(`/api/campaigns/${campaignId}/sequence`)
      .then((data) => {
        if (!active) return;
        setName(data.name || `Sequence for ${campaignId}`);
        setSteps(withUiIds(data.steps || []));
        // Load saved sender if available
        if (data.sender_email) {
          setSelectedSender(data.sender_email);
        }
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message || "Failed to load sequence.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    fetchApi(`/api/campaigns/${campaignId}/sequence/status`)
      .then((data) => {
        if (!active) return;
        setStatus(data.status || null);
      })
      .catch(() => {
        if (!active) return;
        setStatus(null);
      });

    return () => {
      active = false;
    };
  }, [campaignId, fetchApi]);

  const updateStep = (index, updates) => {
    setSteps((prev) =>
      prev.map((step, idx) => (idx === index ? { ...step, ...updates } : step))
    );
  };

  const addStep = (type = "email") => {
    const base = {
      _uiId: makeId(),
      type,
      delay_days: 0
    };
    if (type === "email") {
      base.template = EMAIL_TEMPLATES[0];
    }
    if (type === "call") {
      base.script = "";
    }
    if (type === "linkedin_connect" || type === "linkedin_message") {
      base.message = "";
    }
    setSteps((prev) => [...prev, base]);
  };

  const removeStep = (index) => {
    setSteps((prev) => prev.filter((_, idx) => idx !== index));
  };

  const moveStep = (from, to) => {
    setSteps((prev) => {
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  };

  const handleSave = async () => {
    if (!campaignId) return;
    setSaving(true);
    setError("");
    setStatusMessage("Saving sequence...");
    try {
      await fetchApi(`/api/campaigns/${campaignId}/sequence`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() || `Sequence for ${campaignId}`,
          steps: stripUiIds(steps),
          sender_email: selectedSender
        })
      });
      setStatusMessage("Sequence saved.");
    } catch (err) {
      setStatusMessage("");
      setError(err.message || "Failed to save sequence.");
    } finally {
      setSaving(false);
    }
  };

  // Find the first email step for preview
  const currentEmailStep = useMemo(() => {
    return steps.find(step => step.type === "email") || { subject: "", body: "" };
  }, [steps]);

  return (
    <div className="sequence-builder-layout">
      <div className="builder-panel">
        <div className="sequence-builder">
          <div className="sequence-header">
        <div>
          <h2>Sequence builder</h2>
          <p className="muted">
            Plan multi-step outreach with email, calls, and LinkedIn touches.
          </p>
        </div>
        <div className="sequence-meta">
          <div>
            <p className="sequence-label">Steps</p>
            <strong>{steps.length}</strong>
          </div>
          <div>
            <p className="sequence-label">Total delay</p>
            <strong>{totalDelay} days</strong>
          </div>
        </div>
      </div>

      <div className="sequence-name">
        <label>
          Sequence name
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Outbound sequence"
          />
        </label>
        <label>
          Sequence owner
          <select
            value={selectedSender}
            onChange={(event) => setSelectedSender(event.target.value)}
            className="sender-select"
          >
            {senders.map((sender) => (
              <option key={sender.email} value={sender.email}>
                {sender.name} ({sender.title}) - {sender.email}
              </option>
            ))}
          </select>
        </label>
        <button
          className="primary-button"
          type="button"
          onClick={handleSave}
          disabled={saving || loading}
        >
          {saving ? "Saving..." : "Save sequence"}
        </button>
      </div>

      {statusMessage && <p className="muted">{statusMessage}</p>}
      {error && <p className="error-text">{error}</p>}

      {loading ? (
        <div className="sequence-loading">Loading sequence...</div>
      ) : (
        <>
          <div className="sequence-actions">
            {STEP_TYPES.map((type) => (
              <button
                key={type.value}
                type="button"
                className="secondary-button"
                onClick={() => addStep(type.value)}
              >
                + {type.label}
              </button>
            ))}
          </div>

          {steps.length === 0 ? (
            <div className="sequence-empty">
              <p className="muted">No steps yet. Add your first touch above.</p>
            </div>
          ) : (
            <div className="sequence-steps">
              {steps.map((step, index) => (
                <div className="sequence-step" key={step._uiId}>
                  <div className="sequence-step-head">
                    <div>
                      <p className="sequence-label">Step {index + 1}</p>
                      <select
                        value={step.type}
                        onChange={(event) => updateStep(index, { type: event.target.value })}
                      >
                        {STEP_TYPES.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="sequence-step-actions">
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => moveStep(index, index - 1)}
                        disabled={index === 0}
                      >
                        Up
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        onClick={() => moveStep(index, index + 1)}
                        disabled={index === steps.length - 1}
                      >
                        Down
                      </button>
                      <button
                        type="button"
                        className="ghost-button danger"
                        onClick={() => removeStep(index)}
                      >
                        Remove
                      </button>
                    </div>
                  </div>

                  <div className="sequence-step-body">
                    <label>
                      Delay (days)
                      <input
                        type="number"
                        min="0"
                        value={step.delay_days ?? 0}
                        onChange={(event) =>
                          updateStep(index, { delay_days: Number(event.target.value || 0) })
                        }
                      />
                    </label>

                    {step.type === "email" && (
                      <>
                        <div className="email-settings-row">
                          <div className="personalization-mode-selector">
                            <label>
                              Personalization mode
                              <select
                                value={personalizationMode}
                                onChange={(e) => setPersonalizationMode(e.target.value)}
                                className="prompt-template-select"
                              >
                                <option value="signal_based">Signal-based personalization</option>
                                <option value="fully_personalized">Fully personalized email</option>
                                <option value="personalized_opener">Personalized opener only</option>
                              </select>
                            </label>

                            <div className="mode-description">
                              {personalizationMode === "signal_based" && (
                                <>
                                  <p>Uses intent signals (job postings, equipment, WMS) to create relevant openers. Best for high-volume outreach.</p>
                                  <code className="mode-example">Example: "I noticed Acme recently posted 3 warehouse operations roles..."</code>
                                </>
                              )}
                              {personalizationMode === "fully_personalized" && (
                                <>
                                  <p>AI generates complete email body based on lead data and pain points. Best for high-value prospects. Uses more AI credits.</p>
                                  <code className="mode-example">Example: Complete custom email generated for each recipient</code>
                                </>
                              )}
                              {personalizationMode === "personalized_opener" && (
                                <>
                                  <p>AI generates only the first 1-2 sentences, rest uses your template. Balances personalization with consistency. Recommended for most campaigns.</p>
                                  <code className="mode-example">Example: Custom opener + your template body</code>
                                </>
                              )}
                            </div>
                          </div>

                          <label className="checkbox-label">
                            <input
                              type="checkbox"
                              checked={includeSignature}
                              onChange={(e) => setIncludeSignature(e.target.checked)}
                            />
                            Include signature
                          </label>
                        </div>

                        <VariableAutocomplete
                          label="Subject line"
                          value={step.subject || ""}
                          onChange={(value) => updateStep(index, { subject: value })}
                          variables={variables}
                          placeholder="Warehouse automation for {{company_name}}"
                        />
                        <VariableAutocomplete
                          label="Email body"
                          value={step.body || ""}
                          onChange={(value) => updateStep(index, { body: value })}
                          variables={variables}
                          multiline
                          rows={8}
                          placeholder="Hi {{first_name}},&#10;&#10;{{personalization_sentence}}&#10;&#10;[Your message here]&#10;&#10;Best,&#10;{{sender_name}}"
                        />
                      </>
                    )}

                    {step.type === "call" && (
                      <VariableAutocomplete
                        label="Call script"
                        value={step.script || ""}
                        onChange={(value) => updateStep(index, { script: value })}
                        variables={variables}
                        multiline
                        rows={5}
                        placeholder="Hi {{first_name}}, this is..."
                      />
                    )}

                    {step.type === "linkedin_connect" && (
                      <VariableAutocomplete
                        label="Connection message"
                        value={step.message || ""}
                        onChange={(value) => updateStep(index, { message: value })}
                        variables={variables}
                        multiline
                        rows={4}
                        placeholder="Hi {{first_name}}, thought I'd connect..."
                      />
                    )}

                    {step.type === "linkedin_message" && (
                      <VariableAutocomplete
                        label="LinkedIn message"
                        value={step.message || ""}
                        onChange={(value) => updateStep(index, { message: value })}
                        variables={variables}
                        multiline
                        rows={5}
                        placeholder="Thanks for connecting {{first_name}}..."
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {status && (
        <div className="sequence-status">
          <h3>Sequence status</h3>
          <div className="sequence-status-grid">
            {Object.entries(status).map(([key, count]) => (
              <div className="sequence-status-card" key={key}>
                <p className="sequence-label">{key.replaceAll("_", " ")}</p>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </div>
      )}
        </div>
      </div>

      {/* Email Preview Panel */}
      <div className="preview-panel">
        <EmailLivePreview
          subject={currentEmailStep.subject || ""}
          body={currentEmailStep.body || ""}
          senderEmail={selectedSender}
          campaignId={campaignId}
          fetchApi={fetchApi}
        />
      </div>
    </div>
  );
}

export default SequenceBuilder;
