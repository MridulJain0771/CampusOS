# CampusOS Diagram Catalog

This page collects the main architectural and business diagrams in one place for design reviews and interviews.

## 1. System context

```mermaid
flowchart LR
    Users[Super Admin / School Admin / Teacher / Staff / Parent / Student]
    Web[Admin Web UI]
    API[CampusOS FastAPI]
    DB[(PostgreSQL)]
    Redis[(Redis)]
    Worker[Celery Workers]
    Store[(Object Storage)]
    Providers[Email / SMS / Payment Providers]

    Users --> Web --> API
    API --> DB
    API --> Redis --> Worker
    API -. metadata reference .-> Store
    Worker -. future integrations .-> Providers
```

## 2. Backend module map

```mermaid
flowchart TB
    Main[app.main]
    Auth[Auth + RBAC]
    Schools[Schools]
    People[People]
    Academics[Academics]
    Attendance[Attendance]
    Fees[Fees]
    Lifecycle[Lifecycle]
    Reports[Reports]
    Finance[Finance]
    Community[Community]
    Notifications[Notifications]
    Dashboard[Dashboard]
    DB[(PostgreSQL)]
    Q[(Redis / Celery)]

    Main --> Auth
    Main --> Schools
    Main --> People
    Main --> Academics
    Main --> Attendance
    Main --> Fees
    Main --> Lifecycle
    Main --> Reports
    Main --> Finance
    Main --> Community
    Main --> Notifications
    Main --> Dashboard

    Auth --> DB
    Schools --> DB
    People --> DB
    Academics --> DB
    Attendance --> DB
    Fees --> DB
    Lifecycle --> DB
    Reports --> DB
    Finance --> DB
    Community --> DB
    Notifications --> DB
    Notifications --> Q
    Dashboard --> DB
```

## 3. Tenant boundary

```mermaid
flowchart LR
    JWT[JWT user id] --> User[User row]
    User --> Role[Role]
    User --> SchoolID[school_id]
    SchoolID --> Filter[Every school-scoped query]
    Filter --> TenantRows[(Only tenant rows)]
```

## 4. Academic class relationship

```mermaid
flowchart TD
    Student --> Enrollment
    Year[Academic Year] --> Enrollment
    Enrollment --> Section[Grade + Section]
    Section --> Room[Classroom]
    Section --> ClassTeacher[Class Teacher]
    Section --> Mapping[Subject Teacher Mapping]
    Mapping --> Subject
    Mapping --> SubjectTeacher[Teacher]
    Section --> Timetable
    Timetable --> Subject
    Timetable --> SubjectTeacher
    Timetable --> Room
```

## 5. Core entity relationship view

```mermaid
erDiagram
    SCHOOL ||--o{ USER : owns
    SCHOOL ||--o{ STUDENT : owns
    SCHOOL ||--o{ STAFF : owns
    STUDENT ||--o{ ENROLLMENT : has
    CLASS_SECTION ||--o{ ENROLLMENT : contains
    CLASSROOM ||--o{ CLASS_SECTION : hosts
    STAFF ||--o{ CLASS_SECTION : leads
    CLASS_SECTION ||--o{ CLASS_SUBJECT_TEACHER : maps
    SUBJECT ||--o{ CLASS_SUBJECT_TEACHER : assigned
    STAFF ||--o{ CLASS_SUBJECT_TEACHER : teaches
    STUDENT ||--o{ STUDENT_INVOICE : billed
    STUDENT_INVOICE ||--o{ PAYMENT : receives
    EXAM ||--o{ EXAM_SCORE : has
    STUDENT ||--o{ EXAM_SCORE : receives
    SUBJECT ||--o{ EXAM_SCORE : measured_in
    STAFF ||--o{ SALARY_STRUCTURE : has
    PAYROLL_RUN ||--o{ PAYROLL_ITEM : contains
    STAFF ||--o{ PAYROLL_ITEM : paid_to
```

## 6. Lifecycle state flow

```mermaid
stateDiagram-v2
    [*] --> Admitted: student created
    Admitted --> Active
    Active --> Withdrawn: withdraw
    Withdrawn --> Active: readmit

    [*] --> Joined: staff created
    Joined --> Employed
    Employed --> Terminated: terminate
    Terminated --> Employed: rehire
```

History is append-only in `LifecycleEvent`; `is_active` represents current state.

## 7. Fee lifecycle

```mermaid
flowchart LR
    Structure[Fee Structure] --> Invoice[Student Invoice]
    Invoice --> Lines[Invoice Lines]
    Lines --> Total[Subtotal - Discount + Late Fee]
    Total --> Payment
    Payment -->|partial| Partial[Invoice Partial]
    Payment -->|full| Paid[Invoice Paid]
    Payment --> Refund
    Refund --> Recalc[Recalculate paid amount/status]
```

## 8. Idempotent payment sequence

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant DB

    Client->>API: payment + Idempotency-Key K
    API->>DB: SELECT payment where key=K
    alt existing
        DB-->>API: original payment
        API-->>Client: replay response
    else absent
        API->>DB: INSERT payment(K)
        API->>DB: UPDATE invoice
        API-->>Client: created receipt
    end
```

## 9. Exam/report flow

```mermaid
flowchart LR
    CreateExam --> RecordScores
    RecordScores --> Validate[Validate max/obtained marks]
    Validate --> Calculate[Totals + Percentage + Grade]
    Calculate --> Preview
    Preview --> Publish
    Publish --> Snapshot[(ReportCard Snapshot)]
```

## 10. Payroll and expenditure

```mermaid
flowchart TB
    Staff --> Salary[Effective Salary Structure]
    Salary --> Run[Monthly Payroll Run]
    Run --> Item[Payroll Item Snapshot]
    Item --> Pay[Salary Payment]

    Category[Expense Category] --> Expense[Expense]
    Fees[Net Fee Collections] --> Summary[Finance Summary]
    Pay --> Summary
    Expense --> Summary
```

## 11. Notification flow

```mermaid
flowchart LR
    API --> Record[(Notification Record)]
    API --> Redis[(Redis Broker)]
    Redis --> Worker[Celery Worker]
    Worker --> Provider[External Channel]
    Worker -->|failure| Retry[Celery Retry]
    Retry --> Redis
```

## 12. Local development topology

```mermaid
flowchart LR
    Browser[Browser :5173]
    Frontend[Static Frontend]
    API[FastAPI :8000]
    PG[(PostgreSQL :5432)]
    R[(Redis :6379)]
    W[Celery Worker]
    Tests[Pytest / Ruff / Alembic]

    Browser --> Frontend
    Frontend --> API
    API --> PG
    API --> R
    R --> W
    W --> PG
    Tests --> API
    Tests --> PG
    Tests --> R
```

## 13. CI flow

```mermaid
flowchart LR
    Push[Push / PR] --> Checkout
    Checkout --> Install[Install + pip check]
    Install --> Compile
    Compile --> Ruff
    Ruff --> Migrate[Alembic fresh migration]
    Migrate --> Unit
    Unit --> Integration
    Push --> Docker[Docker build]
    Docker --> NonRoot[Verify non-root user]
```
