import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PatientResults } from "../../app/patients/PatientResults";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function selectMeasurement(verify: () => Promise<unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/verify")) return verify();
      const data = url.endsWith("/patients")
        ? { patients: [{ id: "patient-a", label: "患者 A" }] }
        : {
            measurements: [
              {
                id: "measurement-a",
                observed_at: 1700000000,
                duration: 60,
                status: "recorded",
              },
            ],
          };
      return { ok: true, json: async () => data };
    }),
  );
  render(<PatientResults />);
  await screen.findByRole("option", { name: "患者 A" });
  fireEvent.change(screen.getByLabelText("患者"), {
    target: { value: "patient-a" },
  });
  await screen.findByRole("option", { name: /2023/ });
  fireEvent.change(screen.getByLabelText("計測開始時刻"), {
    target: { value: "measurement-a" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "証明を検証して結果を取得" }),
  );
}

test("valid proof with output zero displays a verified false result", async () => {
  await selectMeasurement(async () => ({
    ok: true,
    json: async () => ({
      status: "verified",
      isNormal: false,
      observedAt: 1700000000,
      durationSeconds: 60,
    }),
  }));
  expect(await screen.findByText("isNormal: false")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("患者"), { target: { value: "" } });
  expect(screen.queryByText("isNormal: false")).not.toBeInTheDocument();
});

test.each(["confirming", "pending", "failed"])(
  "%s never releases an unverified boolean",
  async (status) => {
    await selectMeasurement(async () => ({
      ok: true,
      json: async () => ({ status, isNormal: true }),
    }));
    await screen.findByRole("alert");
    expect(screen.queryByText(/isNormal:/)).not.toBeInTheDocument();
  },
);

test("RPC or verification failure is not rendered as isNormal=false", async () => {
  await selectMeasurement(async () => ({
    ok: false,
    json: async () => ({ detail: "検証できません" }),
  }));
  expect(await screen.findByRole("alert")).toHaveTextContent("検証できません");
  expect(screen.queryByText(/isNormal:/)).not.toBeInTheDocument();
});

test("late verification response cannot replace a changed selection", async () => {
  let resolve!: (response: unknown) => void;
  const deferred = new Promise((r) => {
    resolve = r;
  });
  await selectMeasurement(() => deferred);
  fireEvent.change(screen.getByLabelText("患者"), { target: { value: "" } });
  resolve({
    ok: true,
    json: async () => ({ status: "verified", isNormal: true }),
  });
  await vi.waitFor(() => expect(screen.getByRole("button")).toBeDisabled());
  expect(screen.queryByText(/isNormal:/)).not.toBeInTheDocument();
});
