import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { LanguageSwitcher } from "./LanguageSwitcher";
import { translate, translateStatus, useI18nStore } from "./index";

describe("i18n", () => {
  beforeEach(() => {
    useI18nStore.getState().setLanguage("en");
  });

  it("translates keys with interpolation per language", () => {
    expect(translate("en", "workflows.versionCreated", { version: 3 })).toBe("Created Workflow Version v3.");
    expect(translate("zh", "workflows.versionCreated", { version: 3 })).toBe("已创建工作流版本 v3。");
  });

  it("translates known statuses and falls back to the raw value", () => {
    expect(translateStatus("en", "running")).toBe("Running");
    expect(translateStatus("zh", "running")).toBe("运行中");
    expect(translateStatus("zh", "custom_status")).toBe("CUSTOM STATUS");
  });

  it("switches language, persists it, and re-renders translated labels", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitcher />);
    expect(screen.getByRole("group", { name: "Language" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "中文" }));
    expect(window.localStorage.getItem("relayvia.language")).toBe("zh");
    expect(useI18nStore.getState().language).toBe("zh");
    expect(screen.getByRole("group", { name: "语言" })).toBeInTheDocument();
    expect(translate(useI18nStore.getState().language, "agents.title")).toBe("已有 Agent");
  });
});
