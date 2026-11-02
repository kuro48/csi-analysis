import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

test("real recorded CSI: third party retrieves result after verification", async ({
  page,
  request,
}) => {
  test.skip(
    process.env.E2E_OBSERVATIONS !== "true",
    "Needs the local observation worker and real CSI record",
  );
  const response = await request.get("/api/v2/observations/patients");
  expect(response.ok()).toBeTruthy();
  const { patients } = await response.json();
  let patient: { id: string; label: string } | undefined;
  let measurement: { id: string } | undefined;
  for (const item of patients) {
    const response = await request.get(
      `/api/v2/observations/patients/${item.id}/measurements`,
    );
    const data = await response.json();
    const recorded = data.measurements.find(
      (m: { status: string }) => m.status === "recorded",
    );
    if (recorded) {
      patient = item;
      measurement = recorded;
      break;
    }
  }
  expect(patient).toBeTruthy();
  expect(measurement).toBeTruthy();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/patients");
  await page.getByLabel("患者", { exact: true }).selectOption(patient!.id);
  await page
    .getByLabel("計測開始時刻", { exact: true })
    .selectOption(measurement!.id);
  await expect(page.getByText(/isNormal:/)).toHaveCount(0);
  await page.getByRole("button", { name: "証明を検証して結果を取得" }).click();
  await expect(page.getByText(/isNormal: (true|false)/)).toBeVisible();
  const evidence = resolve(
    __dirname,
    "../../docs/progress/observations/evidence",
  );
  await page.screenshot({
    path: resolve(evidence, "01-patient-result-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: resolve(evidence, "02-patient-result-mobile.png"),
    fullPage: true,
  });
  await page.getByLabel("患者", { exact: true }).selectOption("");
  await expect(page.getByText(/isNormal:/)).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("failed verification never leaves a prior result visible", async ({
  page,
}) => {
  await page.route("**/api/v2/observations/patients", (route) =>
    route.fulfill({ json: { patients: [{ id: "p", label: "UI fixture" }] } }),
  );
  await page.route("**/api/v2/observations/patients/p/measurements", (route) =>
    route.fulfill({
      json: {
        measurements: [
          {
            id: "m",
            observed_at: 1700000000,
            duration: 60,
            status: "recorded",
          },
        ],
      },
    }),
  );
  let count = 0;
  await page.route("**/api/v2/observations/measurements/m/verify", (route) =>
    ++count === 1
      ? route.fulfill({
          json: {
            status: "verified",
            isNormal: false,
            observedAt: 1700000000,
            durationSeconds: 60,
          },
        })
      : route.fulfill({
          status: 422,
          json: { detail: "記録された証明を検証できません" },
        }),
  );
  await page.goto("/patients");
  await page.getByLabel("患者", { exact: true }).selectOption("p");
  await page.getByLabel("計測開始時刻", { exact: true }).selectOption("m");
  await page.getByRole("button", { name: "証明を検証して結果を取得" }).click();
  await expect(page.getByText("isNormal: false")).toBeVisible();
  await page.getByRole("button", { name: "証明を検証して結果を取得" }).click();
  await expect(page.locator("main").getByRole("alert")).toBeVisible();
  await expect(page.getByText(/isNormal:/)).toHaveCount(0);
});
