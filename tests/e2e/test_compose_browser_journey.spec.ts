import { expect, test } from "@playwright/test";

const companyOrigin = process.env.IEP_COMPANY_ORIGIN ?? "http://localhost:5173";
const applicantOrigin =
  process.env.IEP_APPLICANT_ORIGIN ?? "http://localhost:5174";
const companyBearer =
  process.env.IEP_LOCAL_COMPANY_BEARER ?? "local-company-token";

test("company campaign reaches applicant consent and an explicit human decision", async ({
  browser,
}) => {
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const applicantName = `브라우저 지원자 ${suffix}`;
  const applicantEmail = `browser-${suffix}@example.test`;
  const companyContext = await browser.newContext();
  const companyPage = await companyContext.newPage();

  await companyPage.goto(`${companyOrigin}/hiring`);
  await companyPage.getByLabel("기업 Bearer 토큰").fill(companyBearer);
  await companyPage.getByRole("button", { name: "기업 API 연결" }).click();
  await expect(
    companyPage.getByText("local-owner@example.test 연결됨"),
  ).toBeVisible();

  await companyPage.getByLabel("직무명").fill(`백엔드 엔지니어 ${suffix}`);
  await companyPage
    .getByLabel("직무 설명")
    .fill("테넌트 격리와 복구 가능한 면접 시스템을 설계합니다.");
  await companyPage.getByRole("button", { name: "직무 저장" }).click();
  await expect(
    companyPage.getByText("직무가 API에 저장되었습니다."),
  ).toBeVisible();

  await companyPage.getByLabel("평가 기준명").fill("문제 해결");
  await companyPage
    .getByLabel("평가 기준 설명")
    .fill("실제 답변 근거로 문제를 구조화하고 해결한 경험");
  await companyPage.getByRole("button", { name: "평가 기준 게시" }).click();
  await expect(
    companyPage.getByText(/평가 기준 버전 \d+이 게시되었습니다\./),
  ).toBeVisible();

  await companyPage
    .getByLabel("캠페인명")
    .fill(`Compose 브라우저 채용 ${suffix}`);
  const campaignResponsePromise = companyPage.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/v1/campaigns",
  );
  await companyPage.getByRole("button", { name: "캠페인 게시" }).click();
  const campaignResponse = await campaignResponsePromise;
  expect(campaignResponse.ok()).toBeTruthy();
  const campaign = (await campaignResponse.json()) as { campaign_id: string };
  await expect(
    companyPage.getByText("캠페인이 API에 게시되었습니다."),
  ).toBeVisible();

  await companyPage.getByLabel("지원자 이름").fill(applicantName);
  await companyPage.getByLabel("지원자 이메일").fill(applicantEmail);
  const invitationResponsePromise = companyPage.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname ===
        `/v1/campaigns/${campaign.campaign_id}/invitations`,
  );
  await companyPage.getByRole("button", { name: "초대 발송" }).click();
  const invitationResponse = await invitationResponsePromise;
  expect(invitationResponse.ok()).toBeTruthy();
  const invitationBatch = (await invitationResponse.json()) as {
    invitations: Array<{ invitation_id: string }>;
  };
  const invitationId = invitationBatch.invitations[0]?.invitation_id;
  expect(invitationId).toBeTruthy();
  await expect(
    companyPage.getByText("초대 1건이 API에서 접수되었습니다."),
  ).toBeVisible();

  const fixtureResponse = await companyPage.request.get(
    `${companyOrigin}/v1/local/browser-fixtures/campaigns/${campaign.campaign_id}/invitations/${invitationId}`,
    { headers: { Authorization: `Bearer ${companyBearer}` } },
  );
  expect(fixtureResponse.ok()).toBeTruthy();
  const fixture = (await fixtureResponse.json()) as {
    invitation_token: string;
  };

  const applicantContext = await browser.newContext();
  const applicantPage = await applicantContext.newPage();
  await applicantPage.goto(`${applicantOrigin}/access`);
  await applicantPage.getByLabel("초대 코드").fill(fixture.invitation_token);
  await applicantPage.getByRole("button", { name: "초대 확인" }).click();
  await applicantPage.getByLabel("이름").fill(applicantName);
  await applicantPage
    .getByLabel("본인 확인 값")
    .fill("verified-by-invitation-link");
  await applicantPage.getByRole("button", { name: "본인 확인" }).click();
  await applicantPage.getByRole("checkbox", { name: "문서 분석 동의" }).check();
  await applicantPage.getByRole("checkbox", { name: "면접 녹화 동의" }).check();
  await applicantPage.getByRole("checkbox", { name: "AI 평가 동의" }).check();
  await applicantPage.getByRole("button", { name: "동의하고 계속" }).click();
  await expect(
    applicantPage.getByText(/동의가 API에 기록되었습니다\./),
  ).toBeVisible();

  await companyPage.getByRole("link", { name: "사람 검토" }).click();
  await companyPage.getByLabel("초대 ID").fill(invitationId ?? "");
  await companyPage
    .getByLabel("결정 이유")
    .fill("브라우저 E2E에서 회사 담당자가 명시적으로 보류했습니다.");
  await companyPage.getByRole("button", { name: "보류 결정 기록" }).click();
  await expect(
    companyPage.getByText("사람 최종 결정이 기록되었습니다."),
  ).toBeVisible();

  await applicantContext.close();
  await companyContext.close();
});
