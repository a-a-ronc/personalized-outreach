import { useState, useEffect } from "react";
import { DEFAULT_TEMPLATES, TEMPLATE_CATEGORIES, getTemplateById } from "../data/sequenceTemplates";

function SequenceTemplates({ campaignId, fetchApi, onSelectTemplate }) {
  const [templates, setTemplates] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [previewTemplate, setPreviewTemplate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadTemplates();
  }, [campaignId]);

  const loadTemplates = async () => {
    setLoading(true);
    try {
      // Load both system templates and user-saved templates
      const response = await fetchApi("/api/sequence-templates");
      const userTemplates = response.templates || [];

      // Parse JSON steps for each user template (comes as string from database)
      const parsedUserTemplates = userTemplates.map(t => ({
        ...t,
        steps: typeof t.steps === 'string' ? JSON.parse(t.steps) : t.steps
      }));

      // Get set of default template IDs to prevent duplicates
      const defaultIds = new Set(DEFAULT_TEMPLATES.map(t => t.id));

      // Filter out user templates that have same ID as defaults (prevent duplicates)
      const uniqueUserTemplates = parsedUserTemplates.filter(t => !defaultIds.has(t.id));

      // Combine default templates with unique user templates
      setTemplates([...DEFAULT_TEMPLATES, ...uniqueUserTemplates]);
      setError("");
    } catch (err) {
      // If endpoint doesn't exist yet, just use default templates
      setTemplates([...DEFAULT_TEMPLATES]);
      setError("");
    } finally {
      setLoading(false);
    }
  };

  const handleCloneTemplate = async (templateId) => {
    try {
      const template = getTemplateById(templateId) || templates.find(t => t.id === templateId);
      if (!template) {
        setError("Template not found");
        return;
      }

      // If we have a backend endpoint, use it
      try {
        await fetchApi(`/api/sequence-templates/${templateId}/clone`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ campaign_id: campaignId })
        });
      } catch (e) {
        // If endpoint doesn't exist, just pass template to parent
      }

      // Call parent callback with template
      if (onSelectTemplate) {
        onSelectTemplate(template);
      }

      setPreviewTemplate(null);
    } catch (err) {
      setError(err.message || "Failed to clone template");
    }
  };

  const filteredTemplates = selectedCategory === "all"
    ? templates
    : templates.filter(t => t.category === selectedCategory);

  const getStepIcon = (type) => {
    switch (type) {
      case "email": return "📧";
      case "call": return "📞";
      case "linkedin_connect": return "🔗";
      case "linkedin_message": return "💬";
      case "wait": return "⏱️";
      default: return "•";
    }
  };

  const getStepLabel = (step) => {
    switch (step.type) {
      case "email": return `Email: ${step.subject || step.template || "email"}`;
      case "call": return "Phone call";
      case "linkedin_connect": return "LinkedIn connection request";
      case "linkedin_message": return "LinkedIn message";
      case "wait": return `Wait ${step.delay_days} day${step.delay_days !== 1 ? "s" : ""}`;
      default: return step.type;
    }
  };

  return (
    <div className="sequence-templates">
      <div className="templates-header">
        <div>
          <h2>Sequence Templates</h2>
          <p className="muted">Start with a proven sequence template</p>
        </div>
        <button
          className="btn-secondary"
          onClick={() => onSelectTemplate && onSelectTemplate(null)}
        >
          Start from scratch
        </button>
      </div>

      <div className="template-filters">
        <button
          className={`filter-pill ${selectedCategory === "all" ? "active" : ""}`}
          onClick={() => setSelectedCategory("all")}
        >
          All Templates
        </button>
        {TEMPLATE_CATEGORIES.map(cat => (
          <button
            key={cat.id}
            className={`filter-pill ${selectedCategory === cat.id ? "active" : ""}`}
            onClick={() => setSelectedCategory(cat.id)}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {error && <p className="error-text">{error}</p>}

      {loading ? (
        <div className="templates-loading">Loading templates...</div>
      ) : (
        <div className="template-grid">
          {filteredTemplates.map((template, idx) => (
            <div key={`${template.id || 'template'}-${idx}`} className="template-card">
              <div className="template-card-header">
                <h3>{template.name}</h3>
                <span className="template-category-badge">{template.category.replace(/_/g, " ")}</span>
              </div>

              <p className="template-description">{template.description}</p>

              <div className="template-steps">
                <p className="template-steps-label">
                  {template.steps.length} steps
                </p>
                <div className="template-step-preview">
                  {template.steps.slice(0, 5).map((step, idx) => (
                    <span key={idx} className="step-icon" title={getStepLabel(step)}>
                      {getStepIcon(step.type)}
                    </span>
                  ))}
                  {template.steps.length > 5 && (
                    <span className="step-more">+{template.steps.length - 5}</span>
                  )}
                </div>
              </div>

              <div className="template-actions">
                <button
                  className="btn-secondary"
                  onClick={() => setPreviewTemplate(template)}
                >
                  Preview
                </button>
                <button
                  className="btn-primary"
                  onClick={() => handleCloneTemplate(template.id)}
                >
                  Use Template
                </button>
              </div>
            </div>
          ))}

          {filteredTemplates.length === 0 && (
            <div className="templates-empty">
              <p className="muted">No templates found in this category.</p>
            </div>
          )}
        </div>
      )}

      {previewTemplate && (
        <div className="template-modal-overlay" onClick={() => setPreviewTemplate(null)}>
          <div className="template-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{previewTemplate.name}</h2>
              <button className="modal-close" onClick={() => setPreviewTemplate(null)}>✕</button>
            </div>

            <p className="template-description">{previewTemplate.description}</p>

            <div className="template-sequence-flow">
              {previewTemplate.steps.map((step, idx) => (
                <div key={idx} className="sequence-flow-step">
                  <div className="flow-step-icon">
                    {getStepIcon(step.type)}
                  </div>
                  <div className="flow-step-content">
                    <p className="flow-step-label">{getStepLabel(step)}</p>
                    {step.delay_days > 0 && (
                      <p className="flow-step-delay">After {step.delay_days} days</p>
                    )}
                    {step.body && (
                      <p className="flow-step-preview">{step.body.substring(0, 100)}...</p>
                    )}
                    {step.script && (
                      <p className="flow-step-preview">{step.script.substring(0, 100)}...</p>
                    )}
                    {step.message && (
                      <p className="flow-step-preview">{step.message.substring(0, 100)}...</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setPreviewTemplate(null)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={() => handleCloneTemplate(previewTemplate.id)}
              >
                Use This Template
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SequenceTemplates;
