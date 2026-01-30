import { useState, useEffect, useMemo } from "react";

const ICP_FILTERS = ["all", "high", "medium", "low"];
const ENGAGEMENT_FILTERS = ["all", "replied", "opened", "sent", "not_contacted"];

function PeopleTable({ campaignId, fetchApi }) {
  const [people, setPeople] = useState([]);
  const [selectedPeople, setSelectedPeople] = useState(new Set());
  const [icpFilter, setIcpFilter] = useState("all");
  const [engagementFilter, setEngagementFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailPerson, setDetailPerson] = useState(null);

  useEffect(() => {
    loadPeople();
  }, [campaignId]);

  const loadPeople = async () => {
    setLoading(true);
    setError("");

    try {
      let endpoint = `/api/campaigns/${campaignId}/audience?limit=200`;
      const data = await fetchApi(endpoint);
      setPeople(data.people || data.leads || []);
    } catch (err) {
      setError(err.message || "Failed to load people");
      setPeople([]);
    } finally {
      setLoading(false);
    }
  };

  const filteredPeople = useMemo(() => {
    return people.filter(person => {
      // ICP filter
      if (icpFilter !== "all" && person.icp_confidence !== icpFilter) {
        return false;
      }

      // Engagement filter
      if (engagementFilter !== "all") {
        const status = person.engagement_status || "not_contacted";
        if (status !== engagementFilter) return false;
      }

      // Search filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = (person.first_name + " " + person.last_name).toLowerCase().includes(query);
        const matchesCompany = person.company_name?.toLowerCase().includes(query);
        const matchesEmail = person.email?.toLowerCase().includes(query);
        const matchesTitle = person.title?.toLowerCase().includes(query);
        return matchesName || matchesCompany || matchesEmail || matchesTitle;
      }

      return true;
    });
  }, [people, icpFilter, engagementFilter, searchQuery]);

  const handleSelectAll = () => {
    if (selectedPeople.size === filteredPeople.length) {
      setSelectedPeople(new Set());
    } else {
      setSelectedPeople(new Set(filteredPeople.map(p => p.person_key)));
    }
  };

  const handleSelectPerson = (personKey) => {
    const newSelected = new Set(selectedPeople);
    if (newSelected.has(personKey)) {
      newSelected.delete(personKey);
    } else {
      newSelected.add(personKey);
    }
    setSelectedPeople(newSelected);
  };

  const handleBulkAddToSequence = async () => {
    if (selectedPeople.size === 0) return;

    try {
      await fetchApi(`/api/campaigns/${campaignId}/sequence/enroll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          person_keys: Array.from(selectedPeople)
        })
      });

      alert(`${selectedPeople.size} people added to sequence`);
      setSelectedPeople(new Set());
      loadPeople();
    } catch (err) {
      setError(err.message || "Failed to add people to sequence");
    }
  };

  const handleEnrichPerson = async (personKey) => {
    try {
      await fetchApi(`/api/campaigns/${campaignId}/enrich`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ person_keys: [personKey] })
      });

      alert("Enrichment started");
      loadPeople();
    } catch (err) {
      setError(err.message || "Failed to enrich person");
    }
  };

  const getIcpBadge = (confidence) => {
    if (!confidence) return null;
    const colors = {
      high: "status-replied",
      medium: "status-opened",
      low: "status-bounced"
    };
    return (
      <span className={`status-badge ${colors[confidence]}`}>
        {confidence} ICP
      </span>
    );
  };

  const getEngagementBadge = (status) => {
    if (!status || status === "not_contacted") return null;
    const statusMap = {
      replied: "status-replied",
      opened: "status-opened",
      sent: "status-sent"
    };
    return (
      <span className={`status-badge ${statusMap[status] || "status-sent"}`}>
        {status}
      </span>
    );
  };

  return (
    <div className="people-table-container">
      <div className="people-header">
        <div>
          <h2>People</h2>
          <p className="muted">{filteredPeople.length} of {people.length} leads</p>
        </div>
        <div className="people-actions">
          {selectedPeople.size > 0 && (
            <>
              <span className="selected-count">{selectedPeople.size} selected</span>
              <button className="btn-primary" onClick={handleBulkAddToSequence}>
                Add to Sequence
              </button>
            </>
          )}
          <button className="btn-secondary" onClick={loadPeople}>
            Refresh
          </button>
        </div>
      </div>

      <div className="people-filters">
        <input
          type="search"
          className="search-input"
          placeholder="Search people, companies, titles..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />

        <div className="filter-group">
          <span className="filter-label">ICP:</span>
          {ICP_FILTERS.map(filter => (
            <button
              key={filter}
              className={`filter-pill ${icpFilter === filter ? "active" : ""}`}
              onClick={() => setIcpFilter(filter)}
            >
              {filter}
            </button>
          ))}
        </div>

        <div className="filter-group">
          <span className="filter-label">Engagement:</span>
          {ENGAGEMENT_FILTERS.map(filter => (
            <button
              key={filter}
              className={`filter-pill ${engagementFilter === filter ? "active" : ""}`}
              onClick={() => setEngagementFilter(filter)}
            >
              {filter.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      {loading ? (
        <div className="people-loading">Loading people...</div>
      ) : (
        <div className="data-table">
          <div className="table-header">
            <span className="col-checkbox">
              <input
                type="checkbox"
                checked={selectedPeople.size === filteredPeople.length && filteredPeople.length > 0}
                onChange={handleSelectAll}
              />
            </span>
            <span className="col-name">Name</span>
            <span className="col-company">Company</span>
            <span className="col-title">Title</span>
            <span className="col-icp">ICP</span>
            <span className="col-engagement">Engagement</span>
            <span className="col-actions">Actions</span>
          </div>

          {filteredPeople.length === 0 ? (
            <div className="table-empty">
              <p className="muted">No people found matching filters.</p>
            </div>
          ) : (
            filteredPeople.map((person) => (
              <div
                key={person.person_key}
                className="table-row"
                onClick={() => setDetailPerson(person)}
              >
                <span className="col-checkbox" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={selectedPeople.has(person.person_key)}
                    onChange={() => handleSelectPerson(person.person_key)}
                  />
                </span>
                <span className="col-name">
                  <strong>{person.first_name} {person.last_name}</strong>
                  <span className="col-email">{person.email}</span>
                </span>
                <span className="col-company">{person.company_name}</span>
                <span className="col-title">{person.title}</span>
                <span className="col-icp">{getIcpBadge(person.icp_confidence)}</span>
                <span className="col-engagement">{getEngagementBadge(person.engagement_status)}</span>
                <span className="col-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="action-button"
                    onClick={() => handleEnrichPerson(person.person_key)}
                    title="Enrich with Apollo"
                  >
                    ⚡
                  </button>
                </span>
              </div>
            ))
          )}
        </div>
      )}

      {detailPerson && (
        <div className="person-detail-sidebar">
          <div className="sidebar-header">
            <h3>{detailPerson.first_name} {detailPerson.last_name}</h3>
            <button className="sidebar-close" onClick={() => setDetailPerson(null)}>✕</button>
          </div>

          <div className="sidebar-content">
            <div className="detail-section">
              <h4>Contact Info</h4>
              <div className="detail-row">
                <span className="detail-label">Email:</span>
                <span>{detailPerson.email}</span>
              </div>
              {detailPerson.phone && (
                <div className="detail-row">
                  <span className="detail-label">Phone:</span>
                  <span>{detailPerson.phone}</span>
                </div>
              )}
              {detailPerson.linkedin_url && (
                <div className="detail-row">
                  <span className="detail-label">LinkedIn:</span>
                  <a href={detailPerson.linkedin_url} target="_blank" rel="noopener noreferrer">
                    Profile
                  </a>
                </div>
              )}
            </div>

            <div className="detail-section">
              <h4>Company</h4>
              <div className="detail-row">
                <span className="detail-label">Company:</span>
                <span>{detailPerson.company_name}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Title:</span>
                <span>{detailPerson.title}</span>
              </div>
              {detailPerson.seniority && (
                <div className="detail-row">
                  <span className="detail-label">Seniority:</span>
                  <span>{detailPerson.seniority}</span>
                </div>
              )}
            </div>

            <div className="detail-section">
              <h4>Engagement History</h4>
              {detailPerson.last_contacted_at ? (
                <>
                  <div className="detail-row">
                    <span className="detail-label">Last Contact:</span>
                    <span>{new Date(detailPerson.last_contacted_at).toLocaleDateString()}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">Status:</span>
                    <span>{detailPerson.engagement_status}</span>
                  </div>
                </>
              ) : (
                <p className="muted">No outreach sent yet</p>
              )}
            </div>

            <button
              className="btn-primary"
              onClick={() => {
                setSelectedPeople(new Set([detailPerson.person_key]));
                handleBulkAddToSequence();
              }}
            >
              Add to Sequence
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default PeopleTable;
