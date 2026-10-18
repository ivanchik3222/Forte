import { readFileSync } from "fs";
import { resolve } from "path";
import { render, screen, within } from "@testing-library/react";
import { RegulatoryGuide } from "./RegulatoryGuide";
import registry from "../data/regulations.json";
import { regulatoryNotes } from "../data/regulatoryNotes";
import { setLocale, translate } from "../i18n";

test("published rules match the ML registry, including exclusions and disabled scenarios", () => {
  const actual = JSON.parse(readFileSync(resolve(process.cwd(), "../ML/regulations/rules_v1.json"), "utf8"));
  expect(registry).toEqual(actual);
  expect(Object.keys(regulatoryNotes).sort()).toEqual(actual.rules.map((rule: { id: string }) => rule.id).sort());
  for (const rule of registry.rules) {
    const note = regulatoryNotes[rule.id];
    for (const text of [rule.title, rule.basis, note.observed, note.exclusions, note.interpretation].filter(Boolean) as string[]) {
      expect(translate(text, "kk")).not.toBe(text);
      expect(translate(text, "en")).not.toBe(text);
    }
  }
});

test("inactive rules cannot be presented as enabled checks, and the pinned revision is visible", () => {
  setLocale("ru");
  render(<RegulatoryGuide />);
  const enabled = screen.getByRole("region", { name: "Какие признаки проверяем" });
  const manual = screen.getByRole("region", { name: "Что нельзя установить по одному видео" });
  for (const rule of registry.rules) {
    expect(within(rule.auto_enabled ? enabled : manual).getByText(rule.title)).toBeInTheDocument();
    expect(within(rule.auto_enabled ? manual : enabled).queryByText(rule.title)).not.toBeInTheDocument();
  }
  expect(screen.getByText(registry.source.revision)).toBeVisible();
  expect(screen.getByRole("link", { name: "Открыть в «Әділет»" })).toHaveAttribute("href", registry.source.url);
  expect(screen.getByText(/Последующие изменения акта полностью не сверены/)).toBeVisible();
});
