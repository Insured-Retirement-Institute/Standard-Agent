# Fund Transfer API

## Overview
This document defines the **Fund Transfer** transaction as part of the broader IRI Digital First transformation effort. The transaction supports fund-to-fund and segment-based value transfers on annuity and life insurance policies, enabling carriers, distributors, and solution providers to reallocate policy investments through a modern, standardized interface.

The initiative modernizes legacy XML/SOAP-based In-Force Transactions (IFT) into RESTful APIs for secure, scalable, and interoperable processing. It leverages industry standards and provides a unified approach for carriers, distributors, and solution providers.

---

### Business Case
#### Problem Statement
- Legacy fund transfer processing is commonly exposed through tightly coupled XML/SOAP services and carrier‑specific file formats.
- Inconsistent request/response structures across carriers increase onboarding time, integration cost, and operational risk.
- Distributors and solution providers require a predictable, standards‑aligned interface to submit transfers and track processing status.

#### Objectives
- Provide a consistent, standards‑based API for submitting fund transfers across carriers and product types.
- Enable pre‑defined request structures for different transfer styles (amount, percent, full rebalance) to reduce downstream failures.
- Support asynchronous processing with a lifecycle endpoint for status retrieval.
- Deliver predictable JSON payloads aligned with IRI Digital First architecture and OpenAPI 3.1.x.

### Key Features
- RESTful API with JSON input/output.
- Asynchronous processing model with status polling via a dedicated request lifecycle endpoint.
- Unified request schema with correlationId and firm/participant identifiers.
- Supports fund transfers using **specified funds** and **specified segments** (where applicable).
- Standardized response structures: request acknowledgment, processing status, and effective date confirmation.
- Alignment with IRI OpenAPI 3.1.x documentation.
- Conditional validation based on transfer type and amount method.
- Data Dictionary for field-level definitions and code lists.

---

## Supported Transaction Sub-Types
Fund Transfer supports the following transaction sub-types, supplied via the `transactionSubType` query parameter:

### 1. Full One-Time Rebalance
Used to redistribute the entire contract value across funds in a single transaction, reallocating all source funds to specified destination funds at defined percentages.

### 2. Fund Balance Transfer
Moves the entire balance of one or more source funds to one or more destination funds, without specifying a fixed dollar amount or percentage of contract value.

### 3. Percent of Contract Value Transfer
Transfers a specified percentage of the overall contract value from source funds to destination funds.

### 4. Specified Amount Transfer
Transfers a fixed dollar amount from one or more source funds to one or more destination funds.

---

## Endpoints

#### 1. Submit Fund Transfer
- **Method:** POST
- **Path:** `/v1/policies/{policyNumber}/fund-transfers`
- **Purpose:** Submits a fund transfer transaction for a policy, supporting source and destination fund or segment allocations.

#### 2. Retrieve Fund Transfer Request Status (Async Lifecycle)
- **Method:** GET
- **Path:** `/v1/policies/{policyNumber}/fund-transfers/requests/{requestId}`
- **Purpose:** Retrieves the current processing status of a fund transfer request submitted asynchronously.

---

## Schema Overview
The schema generally includes:

- **Root Attributes:** effectiveDate, allocationOption, cusip, nsccParticipantId
- **transactionAmounts:** amountType (FULL_REBALANCE, FUND_BALANCE_TRANSFER, PERCENT_OF_CONTRACT_VALUE, SPECIFIED_AMOUNT), requestedAmount, requestedPercentage
- **funds:** transferFromFunds and transferToFunds arrays, each containing fund-level and optional segment-level details (fundId, assetClass, investmentType, currentRate, maturityDate, fundSegments)
- **fundSegments:** segmentId, requestedAmount, requestedPercentage — with strict mutual-exclusivity rules based on transfer type
- **arrangement:** productCode, arrangementType, arrangementSubType, startDate, endDate, modalAmt, sourceTransferAmountType, destinationTransferAmountType, arrangementSource, arrangementDestination — used for systematic or recurring transfer programs
- **investProduct:** rateLockInfo, isLockedIn — captures rate-lock details for applicable investment products
- **auditTransSummation:** auditTotalType, auditTotal, correlationGuid, correlationIdState — supports audit and reconciliation workflows
- **Producer:** producerNumber, npn, crdNumber — identifies the advisor or producer associated with the transaction
- **Parties:** individual/entity identity, relationships (owner, jointOwner, annuitant, jointAnnuitant, primaryBeneficiary, contingentBeneficiary), paymentForm, allocationPercentage

Each fund transfer request delivers structured acknowledgment and status information supporting the corresponding transfer workflow.

---

## Response Schema Overview

All API operations—across synchronous and asynchronous processing models—adhere to a unified **Error schema**. This ensures consistent error handling, predictable integration behavior, and standardized troubleshooting across all transaction types.

## Success Response Expectations

### Asynchronous APIs
- Return **HTTP 202** upon successful acceptance of the fund transfer request for processing.
- The response includes a `requestId` and `status` field. Consumers should poll the status endpoint using the `requestId` to determine final processing outcome.

### Status Polling
- Return **HTTP 200** with a `GetFundTransferRequestStatus` payload when retrieving the processing status of a submitted request.

---

## Standard Error Schema
Every error response—regardless of transaction type—includes:
- An HTTP status code in the **400–599** range
- A structured and validated **error code**
- A **timestamp** of when the error was generated
- A safe, user-friendly **Message**
- A **field-level** or **rule-level** error collections

---

## Key Fields

| Field | Description |
|-------|-------------|
| **correlationId** | Carries forward the inbound request's correlation ID header to enable end-to-end traceability. |
| **httpStatus** | Numeric HTTP status code (400–599) representing the type and severity of the failure. |
| **code** | Structured identifier in the enforced format: `domain.category.subcategory`. Enables machine-readable error handling. |
| **message** | User‑friendly explanation, safe to display in portals or consumer‑facing applications. |
| **validationErrors** | Array describing domain/business rule violations; each entry requires its own code and message. |

---

## Supported HTTP Error Codes

| Status Code | Description |
|-------------|-------------|
| `400` | Bad Request |
| `401` | Unauthorized |
| `403` | Forbidden |
| `404` | Not Found |
| `405` | Method Not Allowed |
| `406` | Not Acceptable |
| `409` | Conflict — a transaction for this policy is already in progress or a duplicate request has been detected |
| `413` | Payload Too Large |
| `415` | Unsupported Media Type |
| `422` | Unprocessable Entity |
| `429` | Too Many Requests |
| `500` | Internal Server Error |
| `502` | Bad Gateway |
| `503` | Service Unavailable |
| `504` | Gateway Timeout |

---

## Purpose & Benefits
This standardized error structure ensures:
- A **predictable experience** across all APIs (synchronous + asynchronous)
- Clear differentiation between **developer diagnostics** and **user-safe messages**
- Enhanced **traceability** for carriers, distributors, and integrators
- Support for granular **validation feedback** and complex business rule logic
- Easier **monitoring, logging, and cross-system troubleshooting**

---

## OpenAPI Specs
Unified Swagger documentation for this fund transfer endpoint is available in the `openapi-specs/` folder.

---

## Change Submissions and Reporting Issues
- Use the **Issues** tab of the repository to report bugs or enhancement requests.
- **Security issues** should be reported directly to Katherine Dease at **kdease@irionline.org**.
- Follow the standards governance workflow on the main page for contribution guidelines.

---

## Versioning
- Current Version: **v1.1.0**
- Uses semantic versioning for all updates.
- Changes must be documented through commit messages and changelogs.
- Backward-incompatible changes require a major version increment.
- Draft and active versions are labeled per DFA governance.

---

## Code of Conduct
Refer to the repository's **Code of Conduct** and **Style Guide** for contribution standards.

---

## How to Contribute
- Fork the repository and submit pull requests.
- Report issues using the **Issues** tab.
- Join working groups: **hpikus@irionline.org**.

---

## Business Owners
- **Carrier Business Owner:** digitalfirst@irionline.org
- **Distributor Business Owner:** [contact]
- **Solution Provider Business Owner:** [contact]
