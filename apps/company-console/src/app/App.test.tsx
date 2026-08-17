import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";

describe("company application routing", () => {
  it.each([
    ["/hiring", "채용 캠페인 만들기"],
    ["/review/report", "면접 Evidence 보고서"],
    ["/review/timeline", "동기화된 면접 타임라인"],
    ["/review/human", "사람 검토 기록"],
  ])("renders the owned screen for %s", (path, heading) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("navigates through the registered company feature routes", () => {
    render(
      <MemoryRouter initialEntries={["/hiring"]}>
        <App />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("link", { name: "근거 보고서" }));

    expect(
      screen.getByRole("heading", { name: "면접 Evidence 보고서" }),
    ).toBeInTheDocument();
  });
});
