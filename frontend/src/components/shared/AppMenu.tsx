import { useState } from "react";
import { NavLink } from "react-router-dom";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "app-menu__link app-menu__link--active" : "app-menu__link";

/** Global navigation keeps the three main jobs—mapping, compatibility views, and
 * administration—available without asking people to backtrack through a workflow. */
export function AppMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const closeMenu = () => setIsOpen(false);

  return (
    <header className="app-header">
      <div className="app-header__inner">
        <NavLink className="app-brand" to="/" onClick={closeMenu}>
          <span className="app-brand__mark" aria-hidden="true">
            VB
          </span>
          <span>viewBuilder</span>
        </NavLink>

        <button
          type="button"
          className="app-menu__toggle"
          aria-expanded={isOpen}
          aria-controls="primary-navigation"
          onClick={() => setIsOpen((open) => !open)}
        >
          Menu
        </button>

        <nav
          id="primary-navigation"
          className="app-menu"
          data-open={isOpen}
          aria-label="Primary navigation"
        >
          <NavLink end className={navLinkClass} to="/" onClick={closeMenu}>
            Home
          </NavLink>

          <details className="app-menu__group">
            <summary>Build</summary>
            <div className="app-menu__panel">
              <NavLink end className={navLinkClass} to="/" onClick={closeMenu}>
                Choose source table
              </NavLink>
              <NavLink className={navLinkClass} to="/view-definitions" onClick={closeMenu}>
                Compatibility views
              </NavLink>
              <NavLink className={navLinkClass} to="/legacy-shapes/new" onClick={closeMenu}>
                Capture legacy shape
              </NavLink>
            </div>
          </details>

          <details className="app-menu__group">
            <summary>Manage</summary>
            <div className="app-menu__panel">
              <NavLink className={navLinkClass} to="/setup" onClick={closeMenu}>
                Connections
              </NavLink>
              <NavLink className={navLinkClass} to="/enum-translations" onClick={closeMenu}>
                Enum translations
              </NavLink>
              <NavLink className={navLinkClass} to="/runs" onClick={closeMenu}>
                Run history
              </NavLink>
            </div>
          </details>
        </nav>
      </div>
    </header>
  );
}
