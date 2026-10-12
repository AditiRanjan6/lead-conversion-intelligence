import { useState } from "react";
import type { ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  ChevronDown,
  Database,
  GitFork,
  LayoutDashboard,
  Menu,
  X,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import type { Dataset } from "../types";

interface AppLayoutProps {
  children: ReactNode;
  datasets: Dataset[];
  selectedDatasetId: string;
  onDatasetChange: (datasetId: string) => void;
  datasetLoading: boolean;
}

const projectLinks = [
  {
    label: "Growth overview",
    path: "/",
    icon: LayoutDashboard,
  },
  {
    label: "Funnel intelligence",
    path: "/funnel",
    icon: GitFork,
  },
];

export function AppLayout({
  children,
  datasets,
  selectedDatasetId,
  onDatasetChange,
  datasetLoading,
}: AppLayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const selectedDataset = datasets.find(
    (dataset) => dataset.dataset_id === selectedDatasetId,
  );

  return (
    <div className="app-shell">
      {mobileMenuOpen && (
        <button
          className="mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileMenuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark">
            <Activity size={20} strokeWidth={2.3} />
          </span>
          <span className="brand-copy">
            <strong>lead<span>signal</span></strong>
            <small>INTELLIGENCE SUITE</small>
          </span>
          <button
            className="icon-button sidebar-close"
            aria-label="Close navigation"
            onClick={() => setMobileMenuOpen(false)}
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Main navigation">
          {projectLinks.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              className={({ isActive }) =>
                `nav-link ${isActive ? "nav-link-active" : ""}`
              }
              onClick={() => setMobileMenuOpen(false)}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
              {path === "/" && <span className="nav-live-dot" />}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <div className="sidebar-note-icon">
              <BarChart3 size={16} />
            </div>
            <strong>Make every lead count.</strong>
            <span>Clear signals for a healthier pipeline.</span>
          </div>
          <div className="sidebar-version">
            <span className="version-dot" />
            Analytics connected
          </div>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <button
            className="icon-button mobile-menu-button"
            aria-label="Open navigation"
            onClick={() => setMobileMenuOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="topbar-context">
            <span className="topbar-overline">LEAD CONVERSION INTELLIGENCE</span>
            <span className="topbar-title">
              <span className="topbar-title-mark" />
              Pipeline workspace
            </span>
          </div>

          <div className="topbar-actions">
            <label className="dataset-select-wrap">
              <Database size={16} />
              <span className="dataset-select-label">Dataset</span>
              <select
                aria-label="Select analytics dataset"
                value={selectedDatasetId}
                disabled={datasetLoading || datasets.length === 0}
                onChange={(event) => onDatasetChange(event.target.value)}
              >
                {datasets.map((dataset) => (
                  <option key={dataset.dataset_id} value={dataset.dataset_id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="select-chevron" size={14} />
            </label>

            <div
              className="creator-badge"
              role="group"
              aria-label="Created by Aditi Ranjan"
            >
              <span className="creator-avatar">AR</span>
              <span className="creator-byline">
                <span>Created by</span>
                <strong>Aditi Ranjan</strong>
              </span>
              <span className="creator-links">
                <a
                  href="https://www.linkedin.com/in/aditiranjan/"
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Aditi Ranjan on LinkedIn"
                  title="LinkedIn"
                >
                  in
                </a>
                <a
                  href="https://github.com/AditiRanjan6"
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Aditi Ranjan on GitHub"
                  title="GitHub"
                >
                  gh
                </a>
                <a
                  href="https://ai-sales-intelligence-51hp.onrender.com/dashboard"
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Visit the existing project"
                  title="Aditi’s other project"
                >
                  <ArrowUpRight size={13} />
                </a>
              </span>
            </div>
          </div>
        </header>

        <main className="page-main" onClick={() => mobileMenuOpen && setMobileMenuOpen(false)}>
          {selectedDataset && (
            <div className="dataset-context" aria-live="polite">
              <span className="dataset-context-dot" />
              <span>{selectedDataset.name}</span>
              <span className="context-divider">/</span>
              <span className="dataset-type">{selectedDataset.dataset_type} dataset</span>
            </div>
          )}
          {children}
          <footer className="page-footer">
            <span>Lead Conversion Intelligence</span>
            <span>Analytics are scoped to the selected dataset.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
