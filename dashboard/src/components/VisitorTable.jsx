import { useState, useEffect, useMemo } from "react";

const SOURCE_FILTERS = ["all", "diy", "leadfeeder", "reconciled"];
const VISIT_FILTERS = ["all", "1+", "3+", "5+", "10+"];

function VisitorTable({ fetchApi }) {
  const [visitors, setVisitors] = useState([]);
  const [selectedVisitors, setSelectedVisitors] = useState(new Set());
  const [sourceFilter, setSourceFilter] = useState("all");
  const [visitFilter, setVisitFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailVisitor, setDetailVisitor] = useState(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    loadVisitors();
  }, []);

  const loadVisitors = async () => {
    setLoading(true);
    setError("");

    try {
      const params = new URLSearchParams({ limit: "200" });
      if (sourceFilter !== "all") params.set("source", sourceFilter);

      const data = await fetchApi(`/api/visitors?${params}`);
      setVisitors(data.companies || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message || "Failed to load visitors");
      setVisitors([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadVisitors();
  }, [sourceFilter]);

  const filteredVisitors = useMemo(() => {
    return visitors.filter(visitor => {
      // Visit count filter
      if (visitFilter !== "all") {
        const minVisits = parseInt(visitFilter);
        if ((visitor.total_visits || 0) < minVisits) return false;
      }

      // Search filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = visitor.company_name?.toLowerCase().includes(query);
        const matchesDomain = visitor.domain?.toLowerCase().includes(query);
        const matchesIndustry = visitor.industry?.toLowerCase().includes(query);
        return matchesName || matchesDomain || matchesIndustry;
      }

      return true;
    });
  }, [visitors, visitFilter, searchQuery]);

  const handleSelectAll = () => {
    if (selectedVisitors.size === filteredVisitors.length) {
      setSelectedVisitors(new Set());
    } else {
      setSelectedVisitors(new Set(filteredVisitors.map(v => v.company_key)));
    }
  };

  const handleSelectVisitor = (companyKey) => {
    const newSelected = new Set(selectedVisitors);
    if (newSelected.has(companyKey)) {
      newSelected.delete(companyKey);
    } else {
      newSelected.add(companyKey);
    }
    setSelectedVisitors(newSelected);
  };

  const handleFindContacts = async (companyKey) => {
    try {
      await fetchApi(`/api/visitors/${encodeURIComponent(companyKey)}/find-contacts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      alert("Contact search initiated!");
      loadVisitors();
    } catch (err) {
      setError(err.message || "Failed to find contacts");
    }
  };

  const handleViewDetails = async (companyKey) => {
    try {
      const data = await fetchApi(`/api/visitors/${encodeURIComponent(companyKey)}`);
      setDetailVisitor(data);
    } catch (err) {
      setError(err.message || "Failed to load visitor details");
    }
  };

  const getSourceBadge = (source) => {
    const colors = {
      diy: "status-sent",
      leadfeeder: "status-replied",
      reconciled: "status-opened"
    };
    return (
      <span className={`status-badge ${colors[source] || "status-sent"}`}>
        {source}
      </span>
    );
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "—";
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now - date;
      const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffHours < 1) return "Just now";
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return dateStr;
    }
  };

  const formatEmployeeCount = (count) => {
    if (!count) return "—";
    if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
    return count.toString();
  };

  return (
    <div className="people-table-container visitors-table-container">
      <div className="people-header">
        <div>
          <h2>Website Visitors</h2>
          <p className="muted">{filteredVisitors.length} of {total} identified companies</p>
        </div>

        <div className="people-actions">
          {selectedVisitors.size > 0 && (
            <button
              className="primary-button"
              onClick={() => {
                selectedVisitors.forEach(key => handleFindContacts(key));
              }}
            >
              Find Contacts ({selectedVisitors.size})
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="people-filters">
        <input
          type="search"
          className="search-input"
          placeholder="Search companies, domains..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />

        <div className="filter-group">
          <span className="filter-label">Source:</span>
          {SOURCE_FILTERS.map(filter => (
            <button
              key={filter}
              className={`filter-pill ${sourceFilter === filter ? "active" : ""}`}
              onClick={() => setSourceFilter(filter)}
            >
              {filter === "all" ? "All" : filter}
            </button>
          ))}
        </div>

        <div className="filter-group">
          <span className="filter-label">Visits:</span>
          {VISIT_FILTERS.map(filter => (
            <button
              key={filter}
              className={`filter-pill ${visitFilter === filter ? "active" : ""}`}
              onClick={() => setVisitFilter(filter)}
            >
              {filter === "all" ? "All" : filter}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="loading-state">Loading visitors...</div>
      ) : (
        <div className="data-table">
          <div className="table-header">
            <div className="col-checkbox">
              <input
                type="checkbox"
                checked={selectedVisitors.size === filteredVisitors.length && filteredVisitors.length > 0}
                onChange={handleSelectAll}
              />
            </div>
            <div className="col-company">Company</div>
            <div className="col-domain">Domain</div>
            <div className="col-industry">Industry</div>
            <div className="col-visits">Visits</div>
            <div className="col-employees">Size</div>
            <div className="col-source">Source</div>
            <div className="col-last-visit">Last Visit</div>
            <div className="col-actions">Actions</div>
          </div>

          {filteredVisitors.length === 0 ? (
            <div className="empty-state">
              <p>No visitors found</p>
              <p className="muted">Visitor companies will appear here once they visit your website</p>
            </div>
          ) : (
            filteredVisitors.map(visitor => (
              <div
                key={visitor.company_key}
                className={`table-row ${detailVisitor?.company_key === visitor.company_key ? "selected" : ""}`}
                onClick={() => handleViewDetails(visitor.company_key)}
              >
                <div className="col-checkbox" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedVisitors.has(visitor.company_key)}
                    onChange={() => handleSelectVisitor(visitor.company_key)}
                  />
                </div>
                <div className="col-company">
                  <span className="company-name">{visitor.company_name || "Unknown"}</span>
                </div>
                <div className="col-domain">
                  {visitor.domain ? (
                    <a
                      href={`https://${visitor.domain}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="domain-link"
                    >
                      {visitor.domain}
                    </a>
                  ) : "—"}
                </div>
                <div className="col-industry">{visitor.industry || "—"}</div>
                <div className="col-visits">
                  <span className="visit-count">{visitor.total_visits || 0}</span>
                </div>
                <div className="col-employees">{formatEmployeeCount(visitor.employee_count)}</div>
                <div className="col-source">{getSourceBadge(visitor.source)}</div>
                <div className="col-last-visit">{formatDate(visitor.last_visit_at)}</div>
                <div className="col-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="action-btn"
                    onClick={() => handleFindContacts(visitor.company_key)}
                    title="Find contacts at this company"
                  >
                    Find Contacts
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Detail Sidebar */}
      {detailVisitor && (
        <div className="person-detail-sidebar visitor-detail-sidebar">
          <div className="sidebar-header">
            <h3>{detailVisitor.company_name || "Unknown Company"}</h3>
            <button className="sidebar-close" onClick={() => setDetailVisitor(null)}>×</button>
          </div>

          <div className="sidebar-content">
            <div className="detail-section">
              <h4>Company Info</h4>
              <div className="detail-row">
                <span className="detail-label">Domain:</span>
                <span>
                  {detailVisitor.domain ? (
                    <a href={`https://${detailVisitor.domain}`} target="_blank" rel="noopener noreferrer">
                      {detailVisitor.domain}
                    </a>
                  ) : "—"}
                </span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Industry:</span>
                <span>{detailVisitor.industry || "—"}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Employees:</span>
                <span>{formatEmployeeCount(detailVisitor.employee_count)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Country:</span>
                <span>{detailVisitor.country || "—"}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Source:</span>
                <span>{getSourceBadge(detailVisitor.source)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Confidence:</span>
                <span>{Math.round((detailVisitor.confidence_score || 0) * 100)}%</span>
              </div>
            </div>

            <div className="detail-section">
              <h4>Visit Activity</h4>
              <div className="detail-row">
                <span className="detail-label">Total Visits:</span>
                <span>{detailVisitor.total_visits || 0}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Page Views:</span>
                <span>{detailVisitor.total_page_views || 0}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">First Visit:</span>
                <span>{formatDate(detailVisitor.first_visit_at)}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Last Visit:</span>
                <span>{formatDate(detailVisitor.last_visit_at)}</span>
              </div>
            </div>

            {detailVisitor.sessions && detailVisitor.sessions.length > 0 && (
              <div className="detail-section">
                <h4>Recent Sessions</h4>
                <div className="sessions-list">
                  {detailVisitor.sessions.slice(0, 5).map((session, idx) => (
                    <div key={idx} className="session-item">
                      <div className="session-time">{formatDate(session.started_at)}</div>
                      <div className="session-pages">{session.page_count} pages</div>
                      {session.duration_seconds && (
                        <div className="session-duration">
                          {Math.round(session.duration_seconds / 60)} min
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {detailVisitor.contacts && detailVisitor.contacts.length > 0 && (
              <div className="detail-section">
                <h4>Found Contacts</h4>
                <div className="contacts-list">
                  {detailVisitor.contacts.map((contact, idx) => (
                    <div key={idx} className="contact-item">
                      <div className="contact-name">
                        {contact.first_name} {contact.last_name}
                      </div>
                      <div className="contact-title">{contact.title}</div>
                      <div className="contact-email">{contact.email}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              className="btn-primary"
              onClick={() => handleFindContacts(detailVisitor.company_key)}
            >
              Find Contacts
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default VisitorTable;
