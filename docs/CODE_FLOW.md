# CampusOS Code Flow

This document follows actual request paths from the browser/API client through FastAPI dependencies, domain code and storage.

## 1. Application startup

```mermaid
sequenceDiagram
    participant P as Python Process
    participant F as FastAPI
    participant R as Redis
    participant DB as PostgreSQL

    P->>F: import app.main
    F->>F: register middleware + routers
    F->>R: Redis.from_url(...)
    F->>DB: bootstrap_superadmin()
    DB-->>F: existing or created super admin
    F-->>P: application ready
```

On shutdown the Redis client and SQLAlchemy engine are closed/disposed.

## 2. Generic authenticated request

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI Route
    participant DEP as deps.py
    participant SEC as security.py
    participant DB as PostgreSQL

    C->>API: request + Bearer token
    API->>DEP: resolve CurrentUser
    DEP->>SEC: decode JWT
    SEC-->>DEP: subject/user id
    DEP->>DB: load active User
    DB-->>DEP: role + school_id
    DEP->>DEP: check required role
    API->>DB: school-scoped query/update
    DB-->>API: result
    API-->>C: JSON response
```

## 3. Login flow

```text
POST /api/v1/auth/login
  -> validate request body
  -> load User by email
  -> verify password hash
  -> reject inactive/invalid user
  -> create JWT with user id
  -> return access_token
```

Protected requests later load the user again, so a disabled user loses access even if an old token has not yet expired.

## 4. Student enrollment flow

```mermaid
sequenceDiagram
    participant A as School Admin
    participant API as Academics Route
    participant DB as PostgreSQL

    A->>API: POST section/{id}/enrollments
    API->>API: authenticate + authorize + derive school_id
    API->>DB: validate student belongs to school
    API->>DB: validate academic year + section
    API->>DB: INSERT Enrollment
    Note over DB: unique student/year + section/roll constraints
    DB-->>API: enrollment row
    API-->>A: 201 Created
```

Resolving the student's class follows:

```text
Student
  -> active Enrollment
  -> ClassSection
  -> Classroom
  -> class_teacher_staff_id
  -> ClassSubjectTeacher rows
  -> Subject + teacher mappings
```

## 5. Student withdrawal flow

```mermaid
sequenceDiagram
    participant A as Admin
    participant API as Lifecycle Route
    participant DB as PostgreSQL

    A->>API: POST /lifecycle/students/{id}/withdraw
    API->>DB: load school-scoped active student
    API->>DB: set Student.is_active = false
    API->>DB: deactivate active Enrollment rows
    API->>DB: deactivate student IdentityCard
    API->>DB: INSERT LifecycleEvent(withdrawn)
    API->>DB: write audit information
    DB-->>API: committed state
    API-->>A: updated lifecycle response
```

Readmission records a new lifecycle event and restores the current active state; historical events remain unchanged.

## 6. Staff termination flow

```text
POST /api/v1/lifecycle/staff/{id}/terminate
  -> authorize school admin
  -> locate staff inside caller's school
  -> set Staff.is_active = false
  -> disable linked user access when present
  -> deactivate staff identity card
  -> append LifecycleEvent(terminated)
  -> preserve payroll/attendance/history rows
```

## 7. Fee payment flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Fee Route
    participant DB as PostgreSQL

    C->>API: POST invoice/{id}/payments + Idempotency-Key
    API->>DB: find payment by school + idempotency key
    alt replay exists
        DB-->>API: existing payment
        API-->>C: 200 + X-Idempotent-Replay=true
    else new payment
        API->>DB: load invoice + validate school
        API->>DB: INSERT Payment
        API->>DB: update invoice paid_amount/status
        DB-->>API: commit
        API-->>C: 201 payment/receipt
    end
```

The database unique constraint on `(school_id, idempotency_key)` is the final duplicate-payment guard.

## 8. Exam score and report-card flow

```mermaid
flowchart LR
    Exam[Create Exam]
    Scores[Record Subject Scores]
    Calc[Calculate total / percentage / grade]
    Preview[Report Card Preview]
    Publish[Publish Snapshot]
    DB[(ReportCard)]

    Exam --> Scores --> Calc --> Preview --> Publish --> DB
```

A score is unique for exam + student + subject.

Publishing writes a separate `ReportCard` snapshot so later source-record edits do not silently redefine a historical published report.

## 9. Document flow

```text
Client / Admin
  -> create document metadata
  -> validate owner belongs to current school
  -> store category/title/storage URL/dates/important flag
  -> PostgreSQL DocumentRecord

Actual file bytes
  -> external object storage
  -> referenced by storage_url
```

## 10. Payroll generation flow

```mermaid
sequenceDiagram
    participant A as Accountant/Admin
    participant API as Finance Route
    participant DB as PostgreSQL

    A->>API: create payroll run(year, month)
    API->>DB: enforce one school/month run
    API->>DB: load eligible active staff
    API->>DB: select effective salary structure
    loop each staff
        API->>DB: INSERT PayrollItem snapshot
    end
    DB-->>API: payroll run + items
    API-->>A: generated payroll
```

Payment flow:

```text
PayrollItem pending
  -> record payment method/reference/time
  -> status paid
  -> finance summary includes paid payroll
```

## 11. Expense flow

```text
Accountant/Admin
  -> choose ExpenseCategory
  -> POST expense
  -> tenant validation
  -> store amount/vendor/date/method/reference/status
  -> finance summary aggregates paid expenditure
```

## 12. Notification background flow

```mermaid
sequenceDiagram
    participant API as FastAPI
    participant DB as PostgreSQL
    participant R as Redis Broker
    participant W as Celery Worker
    participant X as External Provider

    API->>DB: create notification state
    API->>R: enqueue task
    API-->>API: HTTP request can finish
    R->>W: deliver task
    W->>X: send / process
    alt transient failure
        W->>R: retry
    end
```

## 13. Local frontend flow

When opened through FastAPI:

```text
Browser :8000/admin-ui/
  -> static frontend
  -> same-origin /api/v1
```

When opened separately:

```text
Browser :5173
  -> static frontend
  -> http://localhost:8000/api/v1
  -> FastAPI CORS permits localhost:5173
```

## 14. Test flow

```mermaid
flowchart LR
    Env[PostgreSQL + Redis + .env]
    Mig[Alembic upgrade head]
    Unit[Unit Tests]
    Int[Integration Tests]
    CI[GitHub Actions]

    Env --> Mig --> Unit --> Int
    Unit --> CI
    Int --> CI
```

Integration tests create real tenant/domain rows and exercise authentication, class assignment, fee payment, lifecycle, reports, payroll and expenses against PostgreSQL/Redis-backed application startup.
