import { render, screen } from "@testing-library/react";
import SkylitMetricsSidebar from "./SkylitMetricsSidebar";

test("missing readings do not claim a neutral gamma regime", () => {
  const view = render(<SkylitMetricsSidebar />);
  expect(screen.getByText("Gamma reading unavailable")).toBeInTheDocument();
  expect(screen.queryByText("Neutral γ")).not.toBeInTheDocument();
  view.rerender(<SkylitMetricsSidebar regime="neutral" />);
  expect(screen.getByText("Neutral γ")).toBeInTheDocument();
});
