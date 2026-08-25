"use client";

import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const [light, setLight] = useState(false);

  useEffect(() => {
    setLight(document.documentElement.getAttribute("data-theme") === "light");
  }, []);

  const toggle = () => {
    const next = !light;
    setLight(next);
    if (next) document.documentElement.setAttribute("data-theme", "light");
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("tf-theme", next ? "light" : "dark"); } catch {}
  };

  return (
    <button onClick={toggle} aria-label={light ? "Switch to dark theme" : "Switch to light theme"}
      className="rounded-full border px-3 py-1 text-xs"
      style={{ borderColor: "var(--grid)", color: "var(--ink-secondary)" }}>
      {light ? "◑ dark" : "◐ light"}
    </button>
  );
}
