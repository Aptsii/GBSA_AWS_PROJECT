import { render, screen } from "@testing-library/react";

import { App } from "./App";

it("기업용 애플리케이션 셸을 표시한다", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "기업 면접 관리" })).toBeDefined();
});
