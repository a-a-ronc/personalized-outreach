import { useEffect, useState } from "react";

function EmailLivePreview({ subject, body, senderEmail, campaignId, fetchApi }) {
  const [previewData, setPreviewData] = useState({
    rendered_subject: "",
    rendered_body: "",
    signature: "",
    variables_used: []
  });
  const [sampleLead, setSampleLead] = useState(null);
  const [loading, setLoading] = useState(true);

  // Fetch sample lead data for preview
  useEffect(() => {
    if (!campaignId || !fetchApi) {
      setLoading(false);
      return;
    }

    fetchApi(`/api/campaigns/${campaignId}/audience?limit=1`)
      .then((data) => {
        const leads = data.rows || [];
        if (leads.length > 0) {
          setSampleLead(leads[0]);
        } else {
          // Use default sample data if no leads
          setSampleLead({
            first_name: "John",
            last_name: "Smith",
            title: "VP of Operations",
            company_name: "Acme Logistics",
            industry: "3PL",
            email: "john.smith@acmelogistics.com",
            city: "Salt Lake City",
            state: "Utah"
          });
        }
      })
      .catch(() => {
        // Fallback to default sample
        setSampleLead({
          first_name: "John",
          last_name: "Smith",
          title: "VP of Operations",
          company_name: "Acme Logistics",
          industry: "3PL",
          email: "john.smith@acmelogistics.com",
          city: "Salt Lake City",
          state: "Utah"
        });
      })
      .finally(() => setLoading(false));
  }, [campaignId, fetchApi]);

  // Render preview with variable substitution
  useEffect(() => {
    if (!sampleLead) return;

    // Get sender info for signature
    fetchApi("/api/senders")
      .then((senders) => {
        const sender = senders.find(s => s.email === senderEmail) || senders[0];

        // Build variable map
        const variables = {
          first_name: sampleLead.first_name || "John",
          last_name: sampleLead.last_name || "Smith",
          company_name: sampleLead.company_name || "Acme Corp",
          title: sampleLead.title || "Operations Manager",
          industry: sampleLead.industry || "Logistics",
          email: sampleLead.email || "contact@example.com",
          city: sampleLead.city || "Salt Lake City",
          state: sampleLead.state || "Utah",
          sender_name: sender?.full_name || "Aaron Cendejas",
          sender_email: sender?.email || "aaron@intralog.io",
          sender_title: sender?.title || "Senior Systems Engineer",
          personalization_sentence: "I noticed your recent facility expansion in Utah.",
          pain_statement: "Labor costs cutting into margins",
          credibility_anchor: "We helped a 200k sq ft 3PL reduce pick times by 60%."
        };

        // Replace variables in subject and body
        let renderedSubject = subject || "";
        let renderedBody = body || "";

        Object.keys(variables).forEach(key => {
          const regex = new RegExp(`{{${key}}}`, 'g');
          renderedSubject = renderedSubject.replace(regex, variables[key]);
          renderedBody = renderedBody.replace(regex, variables[key]);
        });

        // Convert newlines to <br> for HTML display
        renderedBody = renderedBody.replace(/\n/g, '<br>');

        setPreviewData({
          rendered_subject: renderedSubject,
          rendered_body: renderedBody,
          signature: sender?.signature_html || "",
          variables_used: Object.keys(variables).filter(key =>
            subject?.includes(`{{${key}}}`) || body?.includes(`{{${key}}}`)
          )
        });
      })
      .catch(() => {
        // Fallback rendering without sender data
        const simpleVars = {
          first_name: sampleLead.first_name || "John",
          company_name: sampleLead.company_name || "Acme Corp"
        };

        let renderedSubject = subject || "";
        let renderedBody = body || "";

        Object.keys(simpleVars).forEach(key => {
          const regex = new RegExp(`{{${key}}}`, 'g');
          renderedSubject = renderedSubject.replace(regex, simpleVars[key]);
          renderedBody = renderedBody.replace(regex, simpleVars[key]);
        });

        renderedBody = renderedBody.replace(/\n/g, '<br>');

        setPreviewData({
          rendered_subject: renderedSubject,
          rendered_body: renderedBody,
          signature: "",
          variables_used: []
        });
      });
  }, [subject, body, senderEmail, sampleLead, fetchApi]);

  if (loading) {
    return (
      <div className="email-preview-panel">
        <div className="preview-header">
          <h3>Email Preview</h3>
        </div>
        <div className="preview-loading">Loading preview...</div>
      </div>
    );
  }

  return (
    <div className="email-preview-panel">
      <div className="preview-header">
        <h3>Email Preview</h3>
        {sampleLead && (
          <span className="preview-recipient">
            To: {sampleLead.first_name} {sampleLead.last_name}
          </span>
        )}
      </div>

      <div className="preview-content">
        {/* Email Subject */}
        <div className="preview-subject">
          <strong>Subject:</strong> {previewData.rendered_subject || <span className="preview-empty">No subject</span>}
        </div>

        {/* Email Body */}
        <div className="preview-body">
          {previewData.rendered_body ? (
            <div dangerouslySetInnerHTML={{ __html: previewData.rendered_body }} />
          ) : (
            <div className="preview-empty">Email body preview will appear here...</div>
          )}
        </div>

        {/* Signature */}
        {previewData.signature && (
          <div className="preview-signature">
            <hr />
            <div dangerouslySetInnerHTML={{ __html: previewData.signature }} />
          </div>
        )}

        {/* Variables Used */}
        {previewData.variables_used.length > 0 && (
          <div className="preview-variables">
            <strong>Variables detected:</strong>
            <div className="variable-tags">
              {previewData.variables_used.map(v => (
                <span key={v} className="variable-tag">{v}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default EmailLivePreview;
