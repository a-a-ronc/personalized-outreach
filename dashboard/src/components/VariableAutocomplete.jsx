import { useEffect, useMemo, useRef, useState } from "react";

const EMPTY_LIST = [];

function groupByCategory(items) {
  const groups = new Map();
  items.forEach((item) => {
    const category = item.category || "Other";
    if (!groups.has(category)) {
      groups.set(category, []);
    }
    groups.get(category).push(item);
  });
  return Array.from(groups.entries());
}

function VariableAutocomplete({
  label,
  value,
  onChange,
  variables,
  placeholder,
  multiline = false,
  rows = 6,
  disabled = false,
  id
}) {
  const wrapperRef = useRef(null);
  const inputRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const list = variables || EMPTY_LIST;
  const safeValue = value ?? "";

  const filtered = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return list;
    return list.filter((item) => {
      const name = (item.name || "").toLowerCase();
      const category = (item.category || "").toLowerCase();
      return name.includes(trimmed) || category.includes(trimmed);
    });
  }, [list, query]);

  const grouped = useMemo(() => groupByCategory(filtered), [filtered]);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (event) => {
      if (!wrapperRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [open]);

  const handleInsert = (name) => {
    const token = `{{${name}}}`;
    const target = inputRef.current;
    if (!target) {
      onChange?.(`${safeValue}${token}`);
      setOpen(false);
      setQuery("");
      return;
    }

    const start = target.selectionStart ?? safeValue.length;
    const end = target.selectionEnd ?? safeValue.length;
    const next = `${safeValue.slice(0, start)}${token}${safeValue.slice(end)}`;
    onChange?.(next);
    requestAnimationFrame(() => {
      target.focus();
      const caret = start + token.length;
      target.setSelectionRange(caret, caret);
    });
    setOpen(false);
    setQuery("");
  };

  const InputTag = multiline ? "textarea" : "input";

  return (
    <div className="variable-field" ref={wrapperRef}>
      <div className="variable-label-row">
        {label && <label htmlFor={id}>{label}</label>}
        <button
          className="variable-trigger"
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          disabled={disabled}
        >
          Insert variable
        </button>
      </div>
      <InputTag
        id={id}
        ref={inputRef}
        value={safeValue}
        onChange={(event) => onChange?.(event.target.value)}
        placeholder={placeholder}
        rows={multiline ? rows : undefined}
        disabled={disabled}
        type={multiline ? undefined : "text"}
      />
      {open && (
        <div className="variable-dropdown">
          <input
            className="variable-search"
            type="search"
            placeholder="Search variables"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {grouped.length === 0 ? (
            <div className="variable-empty">No variables match.</div>
          ) : (
            grouped.map(([category, items]) => (
              <div className="variable-group" key={category}>
                <div className="variable-group-title">{category}</div>
                <div className="variable-items">
                  {items.map((item) => (
                    <button
                      className="variable-item"
                      type="button"
                      key={`${category}-${item.name}`}
                      onClick={() => handleInsert(item.name)}
                    >
                      <span className="variable-name">{item.name}</span>
                      {item.example && (
                        <span className="variable-example">{item.example}</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default VariableAutocomplete;
