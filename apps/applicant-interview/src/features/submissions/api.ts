import type {
  AnalysisReadiness,
  SubmissionCreate,
  SubmissionView,
  UploadIntent,
  UploadIntentCreate,
} from "@interview-evidence/contracts";
import type { BrowserApiClient } from "@interview-evidence/web-client";

import { apiClient } from "../../app/api";

type FileSourceType = "cover_letter" | "resume" | "pdf";
type FileDigest = (file: File) => Promise<string>;

export interface SubmissionApi {
  submitFile(file: File): Promise<SubmissionView>;
  submitRepository(publicUrl: string): Promise<SubmissionView>;
  getReadiness(): Promise<AnalysisReadiness>;
}

export function createSubmissionApi(
  client: BrowserApiClient,
  digestFile: FileDigest = sha256File,
): SubmissionApi {
  return {
    async submitFile(file) {
      const sourceType = fileSourceType(file);
      const digest = await digestFile(file);
      const mediaType = file.type || "application/octet-stream";
      const intentPayload: UploadIntentCreate = {
        byte_size: file.size,
        filename: file.name,
        media_type: mediaType,
        sha256: digest,
        source_type: sourceType,
      };
      const intent = await client.post<UploadIntent, UploadIntentCreate>(
        "/applicant/submissions/upload-intents",
        intentPayload,
        { auth: "applicant" },
      );
      await client.upload(intent.url, file, {
        contentType: mediaType,
        headers: stringHeaders(intent.required_headers),
      });
      const submissionPayload: SubmissionCreate = {
        source_type: sourceType,
        upload_id: intent.upload_id,
      };
      return client.post<SubmissionView, SubmissionCreate>(
        "/applicant/submissions",
        submissionPayload,
        { auth: "applicant" },
      );
    },
    submitRepository(publicUrl) {
      const payload: SubmissionCreate = {
        public_url: publicUrl,
        source_type: "public_git",
      };
      return client.post<SubmissionView, SubmissionCreate>(
        "/applicant/submissions",
        payload,
        { auth: "applicant" },
      );
    },
    getReadiness() {
      return client.get<AnalysisReadiness>("/applicant/analysis-status", {
        auth: "applicant",
      });
    },
  };
}

export const submissionApi = createSubmissionApi(apiClient);

async function sha256File(file: File): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

function fileSourceType(file: File): FileSourceType {
  if (
    file.type === "application/pdf" ||
    file.name.toLowerCase().endsWith(".pdf")
  )
    return "pdf";
  return "resume";
}

function stringHeaders(values: Record<string, unknown>): HeadersInit {
  return Object.fromEntries(
    Object.entries(values).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
