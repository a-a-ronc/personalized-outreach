import { useState } from "react";

function EmailPreview({ campaignId, fetchApi }) {
  const [personKey, setPersonKey] = useState("");
  const [testRecipient, setTestRecipient] = useState("");
  const [previewData, setPreviewData] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);

  const canPreview = Boolean(campaignId && personKey.trim());

  const handlePreview = async () => {
    if (!canPreview) {
      setError("Campaign and person key are required.");
      return;
    }
    setLoading(true);
    setError("");
    setStatus("Generating preview...");
    try {
      const data = await fetchApi(`/api/campaigns/${campaignId}/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ person_key: personKey.trim() })
      });
      setPreviewData(data);
      setStatus("Preview ready.");
    } catch (err) {
      setPreviewData(null);
      setStatus("");
      setError(err.message || "Preview failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleSendTest = async () => {
    if (!canPreview || !testRecipient.trim()) {
      setError("Person key and test recipient email are required.");
      return;
    }
    setSending(true);
    setError("");
    setStatus("Sending test email...");
    try {
      const data = await fetchApi(`/api/campaigns/${campaignId}/test-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          person_key: personKey.trim(),
          test_recipient: testRecipient.trim()
        })
      });
      setStatus(data.message || "Test email sent.");
    } catch (err) {
      setStatus("");
      setError(err.message || "Test email failed.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="email-preview">
      <div className="preview-form">
        <label>
          Person key
          <input
            type="text"
            value={personKey}
            onChange={(event) => setPersonKey(event.target.value)}
            placeholder="paste person_key from leads.db"
          />
        </label>
        <label>
          Test recipient email
          <input
            type="email"
            value={testRecipient}
            onChange={(event) => setTestRecipient(event.target.value)}
            placeholder="you@example.com"
          />
        </label>
        <div className="preview-actions">
          <button
            className="primary-button"
            type="button"
            onClick={handlePreview}
            disabled={!canPreview || loading}
          >
            {loading ? "Generating..." : "Generate preview"}
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={handleSendTest}
            disabled={!canPreview || !testRecipient.trim() || sending}
          >
            {sending ? "Sending..." : "Send test email"}
          </button>
        </div>
        <p className="muted">
          Use a person_key from your `leads_people` table to render a real preview.
        </p>
      </div>

      <div className="preview-output">
        {status && <p className="muted">{status}</p>}
        {error && <p className="error-text">{error}</p>}
        {previewData ? (
          <div className="preview-card">
            <div className="preview-meta">
              <div>
                <p className="preview-label">From</p>
                <strong>{previewData.sender_name}</strong>
                <p className="muted">{previewData.sender_email}</p>
              </div>
              <div>
                <p className="preview-label">To</p>
                <strong>{previewData.recipient_name}</strong>
                <p className="muted">{previewData.recipient_email}</p>
              </div>
            </div>
            <h4>{previewData.subject}</h4>
            <div
              className="preview-html"
              dangerouslySetInnerHTML={{ __html: previewData.body_html }}
            />
            <div className="preview-plain">
              <p className="preview-label">Plain text</p>
              <pre>{previewData.body_plain}</pre>
            </div>
          </div>
        ) : (
          <div className="preview-placeholder">
            <p className="muted">Generate a preview to see the full email rendering.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default EmailPreview;
