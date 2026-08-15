import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { JsonEditor } from "./JsonEditor";

function Harness() {
  const [value, setValue] = useState('{"type":"object"}');
  return <JsonEditor label="Input schema" value={value} onChange={setValue} />;
}

describe("JsonEditor", () => {
  it("formats a valid JSON schema", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Format" }));
    expect(screen.getByRole("textbox")).toHaveValue('{\n  "type": "object"\n}');
  });
});

