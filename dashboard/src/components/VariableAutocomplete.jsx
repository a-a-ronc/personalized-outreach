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
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0 });
  const [selectedIndex, setSelectedIndex] = useState(0);
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

    // If dropdown was triggered by {{, replace the {{ with the full token
    const textBefore = safeValue.slice(0, start);
    const hasBrackets = textBefore.endsWith('{{');
    const replaceStart = hasBrackets ? start - 2 : start;

    const next = `${safeValue.slice(0, replaceStart)}${token}${safeValue.slice(end)}`;
    onChange?.(next);
    requestAnimationFrame(() => {
      target.focus();
      const caret = replaceStart + token.length;
      target.setSelectionRange(caret, caret);
    });
    setOpen(false);
    setQuery("");
  };

  const handleInputChange = (event) => {
    const newValue = event.target.value;
    const target = event.target;
    const cursorPos = target.selectionStart;

    // Check if user just typed {{
    if (newValue.length > safeValue.length && cursorPos >= 2) {
      const textBefore = newValue.slice(0, cursorPos);
      if (textBefore.endsWith('{{')) {
        // Apollo-style: Show dropdown when {{ is typed
        setOpen(true);
        setQuery("");
        setSelectedIndex(0);

        // Calculate dropdown position near cursor
        const rect = target.getBoundingClientRect();
        setDropdownPosition({
          top: rect.top + 30,
          left: rect.left
        });
      }
    }

    onChange?.(newValue);
  };

  const handleKeyDown = (event) => {
    if (!open) return;

    const flatList = filtered;
    const maxIndex = flatList.length - 1;

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setSelectedIndex(prev => (prev < maxIndex ? prev + 1 : 0));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setSelectedIndex(prev => (prev > 0 ? prev - 1 : maxIndex));
        break;
      case 'Enter':
        if (flatList[selectedIndex]) {
          event.preventDefault();
          handleInsert(flatList[selectedIndex].name);
        }
        break;
      case 'Escape':
        event.preventDefault();
        setOpen(false);
        setQuery("");
        break;
    }
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
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={multiline ? rows : undefined}
        disabled={disabled}
        type={multiline ? undefined : "text"}
      />
      {open && (
        <div className="variable-dropdown apollo-dropdown">
          <input
            className="variable-search"
            type="search"
            placeholder="Search variables (or type {{)"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
          />
          {grouped.length === 0 ? (
            <div className="variable-empty">No variables match.</div>
          ) : (
            grouped.map(([category, items]) => (
              <div className="variable-group" key={category}>
                <div className="variable-group-title">{category}</div>
                <div className="variable-items">
                  {items.map((item) => {
                    const globalIndex = filtered.findIndex(v => v.name === item.name);
                    const isSelected = globalIndex === selectedIndex;
                    return (
                      <button
                        className={`variable-item ${isSelected ? 'selected' : ''}`}
                        type="button"
                        key={`${category}-${item.name}`}
                        onClick={() => handleInsert(item.name)}
                        onMouseEnter={() => setSelectedIndex(globalIndex)}
                      >
                        <span className="variable-name">{item.name}</span>
                        {item.example && (
                          <span className="variable-example">{item.example}</span>
                        )}
                      </button>
                    );
                  })}
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
