# Veridocs API Reference

Generated directly from the FastAPI OpenAPI schema (`title=Veridocs API`, `version=0.2.0`).

## Endpoints Overview

| Method | Path | Summary |
| :--- | :--- | :--- |
| `GET` | `/` | Root |
| `GET` | `/analytics` | Get Analytics |
| `GET` | `/api/analytics` | Get Analytics |
| `POST` | `/api/comparisons` | Create Comparison |
| `GET` | `/api/comparisons/{comparison_id}` | Get Comparison Status |
| `GET` | `/api/comparisons/{comparison_id}/events` | Get Comparison Events |
| `GET` | `/api/comparisons/{comparison_id}/export` | Export Comparison |
| `POST` | `/api/documents/upload` | Upload Document Async |
| `GET` | `/api/documents/{document_id}/entities` | Get Document Entities |
| `GET` | `/api/documents/{document_id}/events` | Stream Document Events |
| `GET` | `/api/documents/{document_id}/extraction` | Get Document Extraction |
| `PUT` | `/api/documents/{document_id}/extraction` | Update Document Extraction |
| `GET` | `/api/documents/{document_id}/flags` | Get Document Flags Endpoint |
| `GET` | `/api/documents/{document_id}/graph` | Get Document Graph Endpoint |
| `GET` | `/api/documents/{document_id}/report` | Get Document Report |
| `POST` | `/api/documents/{document_id}/report` | Generate Document Report |
| `GET` | `/api/documents/{document_id}/report/export` | Export Document Report |
| `POST` | `/api/documents/{document_id}/retry` | Retry Document Processing |
| `GET` | `/api/documents/{document_id}/status` | Get Document Status |
| `GET` | `/api/documents/{document_id}/summary` | Get Document Summary |
| `POST` | `/api/documents/{document_id}/summary` | Create Document Summary |
| `GET` | `/api/documents/{document_id}/tables` | Get Document Extracted Tables |
| `PATCH` | `/api/documents/{document_id}/type` | Override Document Type |
| `GET` | `/api/documents/{document_id}/vision` | Get Document Vision |
| `GET` | `/api/documents/{session_id}/pdf` | Get Document Pdf |
| `GET` | `/api/documents/{session_id}/text` | Get Document Text Pages |
| `GET` | `/api/graph` | Search Cross Document Graph Endpoint |
| `GET` | `/api/health` | Health Check |
| `GET` | `/api/llm/status` | Llm Status |
| `POST` | `/api/query` | Query Documents |
| `POST` | `/api/query/stream` | Stream Query Endpoint |
| `POST` | `/api/search` | Cross Document Search |
| `DELETE` | `/api/sessions/{session_id}` | Delete Session Endpoint |
| `GET` | `/api/sessions/{session_id}` | Get Session Info |
| `DELETE` | `/api/sessions/{session_id}/documents/{document_name}` | Delete Document Endpoint |
| `GET` | `/api/sessions/{session_id}/suggestions` | Get Session Suggestions Endpoint |
| `POST` | `/api/upload` | Upload Documents |
| `POST` | `/comparisons` | Create Comparison |
| `GET` | `/comparisons/{comparison_id}` | Get Comparison Status |
| `GET` | `/comparisons/{comparison_id}/events` | Get Comparison Events |
| `GET` | `/comparisons/{comparison_id}/export` | Export Comparison |
| `POST` | `/documents/upload` | Upload Document Async |
| `GET` | `/documents/{document_id}/entities` | Get Document Entities |
| `GET` | `/documents/{document_id}/events` | Stream Document Events |
| `GET` | `/documents/{document_id}/extraction` | Get Document Extraction |
| `PUT` | `/documents/{document_id}/extraction` | Update Document Extraction |
| `GET` | `/documents/{document_id}/flags` | Get Document Flags Endpoint |
| `GET` | `/documents/{document_id}/graph` | Get Document Graph Endpoint |
| `GET` | `/documents/{document_id}/report` | Get Document Report |
| `POST` | `/documents/{document_id}/report` | Generate Document Report |
| `GET` | `/documents/{document_id}/report/export` | Export Document Report |
| `POST` | `/documents/{document_id}/retry` | Retry Document Processing |
| `GET` | `/documents/{document_id}/status` | Get Document Status |
| `GET` | `/documents/{document_id}/summary` | Get Document Summary |
| `POST` | `/documents/{document_id}/summary` | Create Document Summary |
| `GET` | `/documents/{document_id}/tables` | Get Document Extracted Tables |
| `PATCH` | `/documents/{document_id}/type` | Override Document Type |
| `GET` | `/documents/{document_id}/vision` | Get Document Vision |
| `GET` | `/documents/{session_id}/pdf` | Get Document Pdf |
| `GET` | `/documents/{session_id}/text` | Get Document Text Pages |
| `GET` | `/graph` | Search Cross Document Graph Endpoint |
| `POST` | `/search` | Cross Document Search |

## Endpoint Details

### `GET /`

Root

**Responses:** `200`

### `GET /analytics`

Return workspace-wide document, QA verification, and anomaly flag metrics by day.

**Responses:** `200`

### `GET /api/analytics`

Return workspace-wide document, QA verification, and anomaly flag metrics by day.

**Responses:** `200`

### `POST /api/comparisons`

POST /comparisons: Creates a new comparison job between doc_a and doc_b,
enqueues the background analysis task, and returns immediately with the job id.

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /api/comparisons/{comparison_id}`

GET /comparisons/{id}: Returns current status and full diff analysis payload.

**Parameters:**
- `comparison_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/comparisons/{comparison_id}/events`

GET /comparisons/{id}/events: Server-Sent Events (SSE) live stream
of comparison pipeline stage transitions.

**Parameters:**
- `comparison_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/comparisons/{comparison_id}/export`

GET /comparisons/{id}/export: Exports comparison redline and risk report to Markdown.

**Parameters:**
- `comparison_id` (path, required)

**Responses:** `200`, `422`

### `POST /api/documents/upload`

POST /documents/upload: Stores file, creates Document record with status='queued',
enqueues background task, and returns immediately with document_id and status.

**Request Body:** `multipart/form-data`
- Schema: `Body_upload_document_async_api_documents_upload_post`

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/entities`

Retrieve normalized entities extracted from a document, optionally filtered by label.

**Parameters:**
- `document_id` (path, required)
- `label` (query, optional)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/events`

SSE stream of live progress events for document ingestion:
queued -> parsing -> ocr -> chunking -> embedding -> ready | failed.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/extraction`

Retrieve structured schema extraction and field evidence for a document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `PUT /api/documents/{document_id}/extraction`

Save user manual edits on extracted fields without overwriting model output.

**Parameters:**
- `document_id` (path, required)

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/flags`

Retrieve rule-based anomaly flags for human reviewer auditing.
Includes plain-language disclaimer ('signals for human review, not accusations'),
severity breakdown, and evidence quotes with page numbers.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/graph`

Retrieve knowledge graph representation of a document:
Nodes: Party, Organization, Person, Date, MoneyAmount, Clause, Document.
Edges: PARTY_TO, PAYS, OWES, SIGNED_BY, EFFECTIVE_ON, REFERENCES, AMENDS, MENTIONED_IN.

**Parameters:**
- `document_id` (path, required)
- `max_nodes` (query, optional)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/report`

GET /documents/{id}/report: Fetch cached report if previously generated.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `POST /api/documents/{document_id}/report`

POST /documents/{id}/report: Generates a comprehensive cited report from summary,
entities/extraction, anomaly flags, and targeted risk retrieval.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/report/export`

GET /documents/{id}/report/export?format=md|pdf|docx:
Export the generated report as Markdown, PDF, or DOCX.

**Parameters:**
- `document_id` (path, required)
- `format` (query, optional)

**Responses:** `200`, `422`

### `POST /api/documents/{document_id}/retry`

Retry processing for a failed document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/status`

Retrieve current processing status and metadata for a document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/summary`

GET /documents/{id}/summary: Fetch cached summary status and result.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `POST /api/documents/{document_id}/summary`

POST /documents/{id}/summary: Enqueues map-reduce structured summarization job
(or returns cached ready summary unless force=True).

**Parameters:**
- `document_id` (path, required)
- `force` (query, optional)

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/tables`

Return all extracted tables for a document (Markdown and structured JSON).

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `PATCH /api/documents/{document_id}/type`

Allow user to manually override classified document type (e.g. invoice, contract).

**Parameters:**
- `document_id` (path, required)

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /api/documents/{document_id}/vision`

Retrieve multimodal vision analyses for flagged pages of a document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/documents/{session_id}/pdf`

Serve the raw or converted PDF file for in-browser PDF.js rendering.

**Parameters:**
- `session_id` (path, required)
- `document_name` (query, required)

**Responses:** `200`, `422`

### `GET /api/documents/{session_id}/text`

Serve extracted page text for fallback text viewer when PDF rendering is unavailable.

**Parameters:**
- `session_id` (path, required)
- `document_name` (query, required)

**Responses:** `200`, `422`

### `GET /api/graph`

Cross-document graph discovery: trace relationships, contracts, and obligations
associated with an entity across all processed documents.

**Parameters:**
- `entity` (query, optional)
- `max_nodes` (query, optional)

**Responses:** `200`, `422`

### `GET /api/health`

Health check returning real status of embedding model, SQLite DB, and LLM configuration.

**Responses:** `200`

### `GET /api/llm/status`

Return LLM endpoint and model status.

**Responses:** `200`

### `POST /api/query`

Answer a question based on uploaded documents using vector search and LLM.

**Request Body:** `application/json`
- Schema: `QueryRequest`

**Responses:** `200`, `422`

### `POST /api/query/stream`

Stream answer tokens via Server-Sent Events with citations and citation check.

**Request Body:** `application/json`
- Schema: `StreamQueryRequest`

**Responses:** `200`, `422`

### `POST /api/search`

Cross-document hybrid search across the entire document library (when scope='library'
or session_id is omitted) or scoped to a single session. Returns ranked chunks
grouped by document with section_path and page number.

**Request Body:** `application/json`
- Schema: `CrossDocSearchRequest`

**Responses:** `200`, `422`

### `DELETE /api/sessions/{session_id}`

Delete an active session and purge its files and DB records.

**Parameters:**
- `session_id` (path, required)

**Responses:** `200`, `422`

### `GET /api/sessions/{session_id}`

Retrieve session details and document list.

**Parameters:**
- `session_id` (path, required)

**Responses:** `200`, `422`

### `DELETE /api/sessions/{session_id}/documents/{document_name}`

Delete a single document from session.

**Parameters:**
- `session_id` (path, required)
- `document_name` (path, required)

**Responses:** `200`, `422`

### `GET /api/sessions/{session_id}/suggestions`

Retrieve suggested questions for the active session.

**Parameters:**
- `session_id` (path, required)

**Responses:** `200`, `422`

### `POST /api/upload`

Synchronous batch upload for immediate document indexing.

**Request Body:** `multipart/form-data`
- Schema: `Body_upload_documents_api_upload_post`

**Responses:** `200`, `422`

### `POST /comparisons`

POST /comparisons: Creates a new comparison job between doc_a and doc_b,
enqueues the background analysis task, and returns immediately with the job id.

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /comparisons/{comparison_id}`

GET /comparisons/{id}: Returns current status and full diff analysis payload.

**Parameters:**
- `comparison_id` (path, required)

**Responses:** `200`, `422`

### `GET /comparisons/{comparison_id}/events`

GET /comparisons/{id}/events: Server-Sent Events (SSE) live stream
of comparison pipeline stage transitions.

**Parameters:**
- `comparison_id` (path, required)

**Responses:** `200`, `422`

### `GET /comparisons/{comparison_id}/export`

GET /comparisons/{id}/export: Exports comparison redline and risk report to Markdown.

**Parameters:**
- `comparison_id` (path, required)

**Responses:** `200`, `422`

### `POST /documents/upload`

POST /documents/upload: Stores file, creates Document record with status='queued',
enqueues background task, and returns immediately with document_id and status.

**Request Body:** `multipart/form-data`
- Schema: `Body_upload_document_async_documents_upload_post`

**Responses:** `200`, `422`

### `GET /documents/{document_id}/entities`

Retrieve normalized entities extracted from a document, optionally filtered by label.

**Parameters:**
- `document_id` (path, required)
- `label` (query, optional)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/events`

SSE stream of live progress events for document ingestion:
queued -> parsing -> ocr -> chunking -> embedding -> ready | failed.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/extraction`

Retrieve structured schema extraction and field evidence for a document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `PUT /documents/{document_id}/extraction`

Save user manual edits on extracted fields without overwriting model output.

**Parameters:**
- `document_id` (path, required)

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /documents/{document_id}/flags`

Retrieve rule-based anomaly flags for human reviewer auditing.
Includes plain-language disclaimer ('signals for human review, not accusations'),
severity breakdown, and evidence quotes with page numbers.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/graph`

Retrieve knowledge graph representation of a document:
Nodes: Party, Organization, Person, Date, MoneyAmount, Clause, Document.
Edges: PARTY_TO, PAYS, OWES, SIGNED_BY, EFFECTIVE_ON, REFERENCES, AMENDS, MENTIONED_IN.

**Parameters:**
- `document_id` (path, required)
- `max_nodes` (query, optional)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/report`

GET /documents/{id}/report: Fetch cached report if previously generated.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `POST /documents/{document_id}/report`

POST /documents/{id}/report: Generates a comprehensive cited report from summary,
entities/extraction, anomaly flags, and targeted risk retrieval.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/report/export`

GET /documents/{id}/report/export?format=md|pdf|docx:
Export the generated report as Markdown, PDF, or DOCX.

**Parameters:**
- `document_id` (path, required)
- `format` (query, optional)

**Responses:** `200`, `422`

### `POST /documents/{document_id}/retry`

Retry processing for a failed document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/status`

Retrieve current processing status and metadata for a document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /documents/{document_id}/summary`

GET /documents/{id}/summary: Fetch cached summary status and result.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `POST /documents/{document_id}/summary`

POST /documents/{id}/summary: Enqueues map-reduce structured summarization job
(or returns cached ready summary unless force=True).

**Parameters:**
- `document_id` (path, required)
- `force` (query, optional)

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /documents/{document_id}/tables`

Return all extracted tables for a document (Markdown and structured JSON).

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `PATCH /documents/{document_id}/type`

Allow user to manually override classified document type (e.g. invoice, contract).

**Parameters:**
- `document_id` (path, required)

**Request Body:** `application/json`

**Responses:** `200`, `422`

### `GET /documents/{document_id}/vision`

Retrieve multimodal vision analyses for flagged pages of a document.

**Parameters:**
- `document_id` (path, required)

**Responses:** `200`, `422`

### `GET /documents/{session_id}/pdf`

Serve the raw or converted PDF file for in-browser PDF.js rendering.

**Parameters:**
- `session_id` (path, required)
- `document_name` (query, required)

**Responses:** `200`, `422`

### `GET /documents/{session_id}/text`

Serve extracted page text for fallback text viewer when PDF rendering is unavailable.

**Parameters:**
- `session_id` (path, required)
- `document_name` (query, required)

**Responses:** `200`, `422`

### `GET /graph`

Cross-document graph discovery: trace relationships, contracts, and obligations
associated with an entity across all processed documents.

**Parameters:**
- `entity` (query, optional)
- `max_nodes` (query, optional)

**Responses:** `200`, `422`

### `POST /search`

Cross-document hybrid search across the entire document library (when scope='library'
or session_id is omitted) or scoped to a single session. Returns ranked chunks
grouped by document with section_path and page number.

**Request Body:** `application/json`
- Schema: `CrossDocSearchRequest`

**Responses:** `200`, `422`

## Schemas

### `AnalyticsResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `documents_uploaded` | `integer` | No |
| `documents_analyzed` | `integer` | No |
| `questions_asked` | `integer` | No |
| `flags_found` | `integer` | No |
| `avg_verification_score` | `anyOf` | No |
| `by_day` | `array[DailyAnalyticsBucket]` | No |

### `Body_upload_document_async_api_documents_upload_post`

| Field | Type | Required |
| :--- | :--- | :---: |
| `file` | `string` | Yes |
| `session_id` | `anyOf` | No |

### `Body_upload_document_async_documents_upload_post`

| Field | Type | Required |
| :--- | :--- | :---: |
| `file` | `string` | Yes |
| `session_id` | `anyOf` | No |

### `Body_upload_documents_api_upload_post`

| Field | Type | Required |
| :--- | :--- | :---: |
| `files` | `array[string]` | Yes |
| `session_id` | `anyOf` | No |

### `CitationCheckResult`

| Field | Type | Required |
| :--- | :--- | :---: |
| `citation_score` | `number` | No |
| `total_claims` | `integer` | No |
| `supported_claims` | `integer` | No |
| `claims` | `array[ClaimCheckDetail]` | No |
| `has_low_confidence_ocr_warning` | `boolean` | No |

### `CitationInfo`

| Field | Type | Required |
| :--- | :--- | :---: |
| `citation_id` | `integer` | Yes |
| `page` | `integer` | Yes |
| `source_file` | `string` | Yes |
| `highlighted_text` | `string` | Yes |
| `chunk_type` | `anyOf` | No |
| `extraction_method` | `anyOf` | No |
| `ocr_confidence` | `anyOf` | No |
| `section_path` | `anyOf` | No |

### `ClaimCheckDetail`

| Field | Type | Required |
| :--- | :--- | :---: |
| `claim` | `string` | Yes |
| `overlap_score` | `number` | Yes |
| `is_supported` | `boolean` | Yes |
| `matched_page` | `anyOf` | No |
| `source_file` | `anyOf` | No |
| `section_path` | `anyOf` | No |
| `is_low_confidence_ocr` | `boolean` | No |

### `CrossDocSearchRequest`

| Field | Type | Required |
| :--- | :--- | :---: |
| `query` | `string` | Yes |
| `session_id` | `anyOf` | No |
| `scope` | `string` | No |
| `top_k` | `integer` | No |

### `CrossDocSearchResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `query` | `string` | Yes |
| `scope` | `string` | Yes |
| `total_matches` | `integer` | No |
| `documents` | `array[SearchDocumentGroup]` | No |

### `DailyAnalyticsBucket`

| Field | Type | Required |
| :--- | :--- | :---: |
| `date` | `string` | Yes |
| `documents_uploaded` | `integer` | No |
| `documents_analyzed` | `integer` | No |
| `questions_asked` | `integer` | No |
| `flags_found` | `integer` | No |
| `avg_verification_score` | `anyOf` | No |

### `DocumentReportResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `document_id` | `string` | Yes |
| `filename` | `anyOf` | No |
| `executive_summary` | `string` | No |
| `important_findings` | `array[ReportFinding]` | No |
| `risks` | `array[ReportFinding]` | No |
| `recommendations` | `array[ReportFinding]` | No |
| `generated_at` | `anyOf` | No |

### `DocumentSummaryResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `document_id` | `string` | Yes |
| `filename` | `anyOf` | No |
| `status` | `string` | Yes |
| `summary` | `anyOf` | No |
| `verification` | `anyOf` | No |
| `grounding_score` | `anyOf` | No |
| `error` | `anyOf` | No |
| `created_at` | `anyOf` | No |
| `updated_at` | `anyOf` | No |

### `HTTPValidationError`

| Field | Type | Required |
| :--- | :--- | :---: |
| `detail` | `array[ValidationError]` | No |

### `HealthResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `status` | `string` | Yes |
| `version` | `string` | Yes |
| `llm_configured` | `boolean` | Yes |
| `active_sessions` | `integer` | Yes |
| `embedding_model_loaded` | `boolean` | Yes |

### `QueryRequest`

| Field | Type | Required |
| :--- | :--- | :---: |
| `session_id` | `string` | Yes |
| `question` | `string` | Yes |
| `history` | `anyOf` | No |
| `active_files` | `anyOf` | No |

### `QueryResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `answer` | `string` | Yes |
| `sources` | `array[SourceInfo]` | Yes |
| `citations` | `array[CitationInfo]` | No |
| `citation_check` | `anyOf` | No |
| `retrieval_strategy` | `anyOf` | No |

### `ReportCitation`

| Field | Type | Required |
| :--- | :--- | :---: |
| `chunk_id` | `anyOf` | No |
| `page` | `integer` | No |
| `section_path` | `anyOf` | No |
| `quote` | `string` | No |

### `ReportFinding`

| Field | Type | Required |
| :--- | :--- | :---: |
| `title` | `string` | Yes |
| `detail` | `string` | Yes |
| `severity` | `anyOf` | No |
| `category` | `anyOf` | No |
| `citations` | `array[ReportCitation]` | No |

### `SearchChunkMatch`

| Field | Type | Required |
| :--- | :--- | :---: |
| `chunk_id` | `anyOf` | No |
| `content` | `string` | Yes |
| `page` | `integer` | No |
| `section_path` | `anyOf` | No |
| `chunk_type` | `string` | No |
| `score` | `number` | No |

### `SearchDocumentGroup`

| Field | Type | Required |
| :--- | :--- | :---: |
| `document_id` | `anyOf` | No |
| `filename` | `string` | Yes |
| `session_id` | `anyOf` | No |
| `max_score` | `number` | No |
| `matches` | `array[SearchChunkMatch]` | No |

### `SessionInfo`

| Field | Type | Required |
| :--- | :--- | :---: |
| `session_id` | `string` | Yes |
| `created_at` | `number` | Yes |
| `file_names` | `array[string]` | Yes |
| `chunk_count` | `integer` | Yes |
| `suggested_questions` | `array[string]` | No |

### `SourceInfo`

| Field | Type | Required |
| :--- | :--- | :---: |
| `page` | `integer` | Yes |
| `snippet` | `string` | Yes |
| `source_file` | `string` | No |
| `relevance_score` | `anyOf` | No |
| `chunk_type` | `anyOf` | No |
| `extraction_method` | `anyOf` | No |
| `section_path` | `anyOf` | No |

### `StreamQueryRequest`

| Field | Type | Required |
| :--- | :--- | :---: |
| `session_id` | `string` | Yes |
| `question` | `string` | Yes |
| `history` | `anyOf` | No |
| `active_files` | `anyOf` | No |

### `StructuredSummaryPayload`

| Field | Type | Required |
| :--- | :--- | :---: |
| `main_purpose` | `string` | No |
| `important_points` | `array[string]` | No |
| `key_information` | `array[string]` | No |
| `conclusion` | `string` | No |

### `SummaryRequest`

| Field | Type | Required |
| :--- | :--- | :---: |
| `force` | `boolean` | No |

### `UploadResponse`

| Field | Type | Required |
| :--- | :--- | :---: |
| `session_id` | `string` | Yes |
| `chunk_count` | `integer` | Yes |
| `processed_files` | `integer` | Yes |
| `failed_files` | `array[string]` | Yes |
| `message` | `string` | Yes |
| `suggested_questions` | `array[string]` | No |
| `document_metadata` | `anyOf` | No |

### `ValidationError`

| Field | Type | Required |
| :--- | :--- | :---: |
| `loc` | `array[any]` | Yes |
| `msg` | `string` | Yes |
| `type` | `string` | Yes |
