import { render, screen } from "@testing-library/react";

import { App } from "./App";

it("지원자용 애플리케이션 셸을 표시한다", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "지원자 AI 면접" })).toBeDefined();
});
