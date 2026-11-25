# System Architecture

## 1. Overview

**Order Intake & Stock Copilot** is a lightweight order-processing backend and operational assistant designed for wholesale suppliers (e.g., HoReCa distributors serving bars and restaurants).

It automates the intake of unstructured orders sent via Telegram (free-form text, voice messages, and chat screenshots), structures them via an LLM, matches items against an SKU catalog, normalizes units into base pieces (`pcs`), verifies real-time stock balances, guides missing/ambiguous details through a clarification step, and routes validated drafts to a manager for approval and accounting export.

---

## 2. Technology Stack

* **Backend & REST API:** Python 3.11+, FastAPI, Uvicorn
* **Database & ORM:** PostgreSQL 16 (Docker), SQLAlchemy 2.x, Alembic
* **Manager Dashboard UI:** Server-rendered Jinja2 templates + HTMX + minimal CSS
* **Telegram Bot Interface:** `aiogram` 3.x (long polling for local development)
* **AI / Parsing Layer:** Structured Outputs LLM (text & vision) + Speech-to-Text (Whisper)
* **Catalog & Export Integration:** `openpyxl` for importing catalog/stock sheets and generating `.xlsx` order exports

---

## 3. High-Level Component Diagram

```text
+--------------------+        +---------------------------------------------+
|   Telegram Bot     |        |             Manager Web UI                  |
|    (aiogram 3)     |        |        (FastAPI + Jinja2 + HTMX)            |
+---------+----------+        +----------------------+----------------------+
          |                                          |
          +--------------------+---------------------+
                               |
                               v
+---------------------------------------------------------------------------+
|                        Application Service Layer                          |
|  - Access Control (Whitelist & Roles)                                     |
|  - Intake & LLM Structured Parser (Text / Voice / Image)                  |
|  - Catalog & Client Matcher + Unit Normalizer (to base pcs)               |
|  - Stock Checker & Order State Machine                                    |
|  - 1C Excel Exporter & Audit Logger                                       |
+------------------------------------+--------------------------------------+
                                     |
                                     v
+---------------------------------------------------------------------------+
|                         PostgreSQL Database                               |
|  users | clients | products | stock_balances | orders | order_items |     |
|  audit_log                                                                |
+---------------------------------------------------------------------------+
```

### Architectural Principles
* **Shared Service Layer:** Both the Telegram bot and the FastAPI endpoints/UI call the same domain services (`app/services/`), keeping business rules centralized and easy to test.
* **Single Source of Truth:** All order states, line items, stock snapshots, and audit events live in PostgreSQL.
* **Zero Hallucination Policy:** The LLM extracts fields and proposes candidate matches, but never invents SKUs or quantities. Unmatched or low-confidence items are explicitly flagged for user/manager review.

---

## 4. Access Control & Roles

Access to the bot and manager interface is restricted via an explicit whitelist stored in the `users` table (`tg_user_id`, `role`, `is_active`).

| Role | Capabilities |
| :--- | :--- |
| **`client`** | Submits incoming order requests (text, voice, image), responds to clarification prompts for their own orders, and views order status updates. |
| **`manager`** | Reviews incoming and pending orders, resolves stock shortages or unrecognized items, edits line items, approves or rejects orders, and downloads accounting exports. |
| **`admin`** | Full manager permissions plus user whitelist management and catalog/stock batch uploads. |

Unauthorized users receive a generic access-denied response, and the attempt is recorded in `audit_log`.

---

## 5. End-to-End Order Processing Flow

1. **Intake & Normalization (`PARSED`):**
   * User sends a text message, voice note, or screenshot in Telegram (or submits via API).
   * Voice messages are transcribed via STT; screenshots are processed via multimodal LLM vision.
   * The LLM returns a strict JSON payload containing `client`, `delivery_address`, `delivery_date`, `payment_terms`, and `items` (`raw_name`, `qty`, `unit`, `confidence`).
   * The raw payload (`raw_input`) is persisted immediately so no incoming order is lost even if downstream steps require manual intervention.
2. **Client & Catalog Matching + Unit Conversion:**
   * Client name/aliases are matched against `clients`.
   * Each line item is matched against `products` (by SKU, exact name, or aliases).
   * Quantities are converted to base units (`pcs`) using `pack_to_base_factor` (e.g., `2 packs` of 24 bottles $\rightarrow$ `48 pcs`).
   * Each line item receives a `match_status`: `matched`, `ambiguous`, or `unrecognized`.
3. **Clarification Loop (`AWAITING_CLARIFICATION`):**
   * Triggered when required order fields are missing (e.g., delivery date, address, or quantity) or when an item is `ambiguous` / `unrecognized`.
   * The bot sends a concise prompt (with inline option buttons when multiple SKU candidates exist).
   * Once the user replies, the draft is updated and re-evaluated.
4. **Stock Verification (`STOCK_CHECKED` $\rightarrow$ `PENDING_MANAGER`):**
   * Normalized line quantities (`normalized_qty_pcs`) are compared against `stock_balances`.
   * Each item receives a `stock_status`:
     * `ok`: requested quantity is fully available.
     * `partial`: available stock is greater than `0` but less than requested.
     * `out_of_stock`: available stock is `0`.
     * `unknown`: item is not yet matched to a catalog SKU.
   * The order moves to `pending_manager` with clear flags highlighting any stock discrepancies.
5. **Manager Review & Finalization (`CONFIRMED` / `REJECTED`):**
   * The manager reviews the order card in the Web UI (or Telegram notification), adjusts quantities/substitutions if needed, and clicks **Approve** or **Reject**.
   * **On `CONFIRMED`:** generates an `.xlsx` export file formatted for accounting/1C import, notifies the operations chat and assigned manager, and logs the event in `audit_log`.
   * **On `REJECTED`:** records the rejection in `audit_log` and closes the active workflow.

---

## 6. Order & Line-Item State Machine

### Order Statuses (`orders.status`)
```text
[Incoming Message]
        |
        v
    (PARSED)
        |
        +--- Missing fields / ambiguous SKU ---> (AWAITING_CLARIFICATION)
        |                                                |
        +<-------------- User reply received ------------+
        |
        v
 (STOCK_CHECKED) ---> (PENDING_MANAGER)
                            |
              +-------------+-------------+
              |                           |
              v                           v
         (CONFIRMED)                 (REJECTED)
              |                           |
              +-------------+-------------+
                            |
                            v
                       (ARCHIVED)
```

### Line-Item Statuses (`order_items`)
* **`match_status`:** `matched` | `ambiguous` | `unrecognized`
* **`stock_status`:** `ok` | `partial` | `out_of_stock` | `unknown`
* **`needs_clarification`:** boolean flag driving UI badges and bot follow-up prompts.

---

## 7. Data Model Summary

* **`users`:** Whitelisted Telegram accounts, roles (`client`, `manager`, `admin`), and active flags.
* **`clients`:** Customer venues, aliases, delivery addresses, default payment terms, and assigned manager.
* **`products`:** Master SKU catalog, search aliases, base unit (`pcs`), and pack conversion factors.
* **`stock_balances`:** Latest available stock per SKU in base units (`quantity_pcs`) and import batch metadata.
* **`orders`:** Order header, source channel (`text`/`voice`/`image`), raw input, delivery/payment terms, and workflow status.
* **`order_items`:** Parsed items, requested vs. normalized quantities, match status, and stock availability status.
* **`audit_log`:** Immutable trail of intake, parsing, clarifications, stock checks, approvals, and access denials.

---

## 8. Reliability & Edge-Case Handling

* **LLM / STT Failures:** Timeouts or invalid model outputs are caught gracefully; the raw message is saved for manual review without crashing the bot or API.
* **Idempotency:** Duplicate Telegram update IDs or repeated webhook/polling deliveries are deduplicated so an order is never created twice.
* **Catalog & Stock Refresh:** Stock snapshots can be re-imported at any time from `.xlsx`/`.csv` files without breaking existing historical orders.