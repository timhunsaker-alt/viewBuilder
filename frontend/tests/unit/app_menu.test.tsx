import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppMenu } from "../../src/components/shared/AppMenu";

describe("AppMenu", () => {
  it("groups all primary workflows in an accessible navigation menu", () => {
    render(
      <MemoryRouter initialEntries={["/view-definitions"]}>
        <AppMenu />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(screen.getByText("Build")).toBeInTheDocument();
    expect(screen.getByText("Manage")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Compatibility views" })).toHaveClass(
      "app-menu__link--active",
    );
  });

  it("has a menu control for the compact navigation layout", () => {
    render(
      <MemoryRouter>
        <AppMenu />
      </MemoryRouter>,
    );

    const toggle = screen.getByRole("button", { name: "Menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});
