import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";

describe("applicant application routing", () => {
  it.each([
    ["/access", "면접 시작 전 확인"],
    ["/submissions", "지원 자료 제출"],
    ["/equipment-check", "장비 및 네트워크 점검"],
    ["/interview", "구조화 면접실"],
  ])("renders the owned screen for %s", (path, heading) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("navigates through the registered applicant feature routes", () => {
    render(
      <MemoryRouter initialEntries={["/access"]}>
        <App />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("link", { name: "지원 자료 제출" }));

    expect(
      screen.getByRole("heading", { name: "지원 자료 제출" }),
    ).toBeInTheDocument();
  });
});
