import type {
  AnalysisReadiness,
  SubmissionView,
  UploadIntent,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";
import { describe, expect, it, vi } from "vitest";

import { createSubmissionApi } from "../api";

describe("submission API", () => {
  it("creates an upload intent, uploads bytes and registers the submission", async () => {
    const intent: UploadIntent = {
      expires_at: "2026-08-18T01:00:00Z",
      method: "PUT",
      required_headers: { "x-content-sha256": "digest" },
      upload_id: "upload-1",
      url: "https://uploads.example.com/upload-1",
    };
    const submission: SubmissionView = {
      created_at: "2026-08-18T00:00:00Z",
      source_type: "pdf",
      status: "received",
      submission_id: "submission-1",
    };
    const post = vi
      .fn()
      .mockResolvedValueOnce(intent)
      .mockResolvedValueOnce(submission);
    const upload = vi.fn().mockResolvedValue(undefined);
    const file = new File(["portfolio"], "portfolio.pdf", {
      type: "application/pdf",
    });
    const api = createSubmissionApi(
      { post, upload } as unknown as BrowserApiClient,
      vi.fn().mockResolvedValue("a".repeat(64)),
    );

    await expect(api.submitFile(file)).resolves.toEqual(submission);

    expect(post).toHaveBeenNthCalledWith(
      1,
      "/applicant/submissions/upload-intents",
      expect.objectContaining({
        byte_size: file.size,
        filename: "portfolio.pdf",
        media_type: "application/pdf",
        sha256: "a".repeat(64),
        source_type: "pdf",
      }),
      { auth: "applicant" },
    );
    expect(upload).toHaveBeenCalledWith(
      intent.url,
      file,
      expect.objectContaining({ contentType: "application/pdf" }),
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      "/applicant/submissions",
      { source_type: "pdf", upload_id: "upload-1" },
      { auth: "applicant" },
    );
  });

  it("registers a public repository and reads analysis readiness", async () => {
    const submission: SubmissionView = {
      created_at: "2026-08-18T00:00:00Z",
      source_type: "public_git",
      status: "analyzing",
      submission_id: "submission-2",
    };
    const readiness: AnalysisReadiness = {
      interview_ready: true,
      overall_status: "partial",
      submissions: [submission],
      impact_summary: "문서 일부가 실패했지만 면접은 진행할 수 있습니다.",
      strategy_id: "strategy-1",
      strategy_version: 1,
    };
    const post = vi.fn().mockResolvedValue(submission);
    const get = vi.fn().mockResolvedValue(readiness);
    const api = createSubmissionApi({
      get,
      post,
    } as unknown as BrowserApiClient);

    await api.submitRepository("https://github.com/example/public-repo");
    await expect(api.getReadiness()).resolves.toEqual(readiness);

    expect(post).toHaveBeenCalledWith(
      "/applicant/submissions",
      {
        public_url: "https://github.com/example/public-repo",
        source_type: "public_git",
      },
      { auth: "applicant" },
    );
    expect(get).toHaveBeenCalledWith("/applicant/analysis-status", {
      auth: "applicant",
    });
  });
});
