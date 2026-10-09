/**
 * @jest-environment jsdom
 */

import React from "react";
import { render } from "@testing-library/react";
import {
  FlipZonesPanel, StackedNodesPanel, TugOfWarPanel,
  ScenarioPanel, RiskDashboardPanel, OpportunitiesPanel,
  ImpliedMovePanel, VolAnalyticsPanel,
  GreekReferencePanel, UsagePanel, LivePolicyPanel,
} from "./SidebarPanels";

describe("SidebarPanels — null prop smoke tests", () => {
  test.each([
    ["FlipZonesPanel", FlipZonesPanel],
    ["StackedNodesPanel", StackedNodesPanel],
    ["TugOfWarPanel", TugOfWarPanel],
    ["ScenarioPanel", ScenarioPanel],
    ["RiskDashboardPanel", RiskDashboardPanel],
    ["OpportunitiesPanel", OpportunitiesPanel],
    ["ImpliedMovePanel", ImpliedMovePanel],
    ["VolAnalyticsPanel", VolAnalyticsPanel],
    ["GreekReferencePanel", GreekReferencePanel],
    ["UsagePanel", UsagePanel],
    ["LivePolicyPanel", LivePolicyPanel],
  ])("%s renders without crashing on null/undefined props", (name, Panel) => {
    if (!Panel) {
      return;
    }
    const { container } = render(<Panel data={null} loading={false} error={null} />);
    expect(container).toBeTruthy();
  });
});

describe("ScenarioPanel — conditional regime wording (LEGACY-03)", () => {
  test.each([
    ["positive", "Positive-gamma backdrop for mean-reversion; needs observed holding at the wall."],
    ["negative", "Negative-gamma backdrop for momentum; needs observed continuation through the wall."],
  ])("regime %s explains conditionally without dealer intent", (regime, sentence) => {
    const { queryByText } = render(
      <ScenarioPanel
        data={{ nodes: { regime, king: { strike: 790 } }, spot: 775 }}
        loading={false}
        error={null}
      />
    );
    expect(queryByText(sentence)).toBeTruthy();
    expect(queryByText(/Dealers/i)).toBeNull();
  });
});
