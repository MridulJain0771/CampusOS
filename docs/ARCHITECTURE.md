# CampusOS Architecture

CampusOS is designed as a multi-tenant school-management SaaS. Every school-scoped record carries `school_id`, and API queries derive the tenant from the authenticated user instead of accepting an arbitrary tenant from the client.

## Domain model

```mermaid
flowchart TD
    Platform[Platform Super Admin] --> School[School / Tenant]
    School --> Users[Users + RBAC]
    School --> People[Students / Parents / Staff]
    School --> Academics[Academic Years / Classes / Rooms / Subjects]
    School --> Finance[Fees / Payroll / Expenses]
    School --> Reports[Exams / Scores / Report Cards / Documents]
    School --> Community[Posts / Announcements / Events]
    School --> Ops[Lifecycle / Attendance / Notifications / Audit Logs]

    Academics --> Section[Class Section]
    Section --> Room[Classroom]
    Section --> Teacher[Class Teacher]
    Section --> Enrollment[Student Enrollments]
    Section --> Subject[Subject Teachers]
    Section --> Timetable[Timetable]
```

## Class-management relationship

A student is not attached directly to a grade string. An `Enrollment` joins a student, academic year and class section. The section links to its physical classroom and class teacher. Subject assignments then attach each subject to the teacher responsible for that class. Timetable entries bind section + subject + teacher + room + time.

This supports questions such as:

- Which class is this student in this academic year?
- Which classroom is Grade 8-A using?
- Who is the class teacher?
- Who teaches Science to Grade 8-A?
- Which students belong to the section?
- Where and when is the next Science period?

## Roles

- `super_admin`: manages schools/tenants.
- `school_admin`: manages one school.
- `accountant`: fee, payroll and expenditure operations.
- `teacher`: academic/report/community/attendance access.
- `staff`: school operations.
- `student`: student-facing access.
- `parent`: guardian-facing access.

Role checks happen at the route boundary. Tenant checks are applied in school-scoped queries.

## Fee ledger

```mermaid
flowchart LR
    FS[Fee Structure] --> INV[Student Invoice]
    INV --> LINE[Invoice Lines]
    INV --> PAY[Payment]
    PAY --> RCPT[Receipt Number]
    PAY --> REF[Refund]
```

Payments use an `Idempotency-Key` unique inside the school so network retries do not create duplicate financial records. Invoice payment state moves through `open -> partial -> paid`. Refunds reduce the paid amount and reopen the invoice state when necessary.

## Lifecycle management

`LifecycleEvent` preserves admission, joining, withdrawal, termination, readmission and rehire history instead of overwriting why someone became inactive. `Student.is_active` and `Staff.is_active` stay as the fast current-state flags. Student withdrawal also deactivates active class enrollments and student ID cards; staff termination deactivates account access and staff ID cards.

## Documents and academic reports

`DocumentRecord` stores metadata and an object-storage reference instead of binary documents in PostgreSQL. Records can belong to the school, a student or a staff member and can be marked important with issue/expiry dates.

`ExamScore` is unique per exam, student and subject. Report cards are calculated from subject scores, then `ReportCard` stores a publish-time snapshot with total marks, percentage, overall grade and teacher remarks. This prevents later salary or score workflow changes from silently rewriting historical published reports.

## Payroll and expenditure

`SalaryStructure` is effective-dated so salary revisions preserve history. A monthly `PayrollRun` creates `PayrollItem` snapshots for active staff, keeping the exact basic salary, allowances, deductions, gross and net values used in that month. Payments store method/reference and paid timestamp.

`ExpenseCategory` and `Expense` track non-payroll expenditure such as utilities, maintenance, events or supplies. The finance summary combines net fee collections, payroll paid and other paid expenditure into a simple operating view.

## Reliability and operations

- PostgreSQL is the source of truth.
- Redis is used by Celery and readiness checks.
- Celery provides background notification delivery/retry semantics.
- Alembic owns schema evolution.
- Audit logs capture sensitive admin actions.
- Liveness and dependency-aware readiness endpoints support deployments.
- Docker runs the API as a non-root user.
- GitHub Actions validates dependencies, Python compilation, Ruff, migrations, unit tests, integration tests and Docker build.

## Production extensions

A larger deployment could add direct S3 upload/presigned URLs, payment-gateway webhooks, SMS/email providers, row-level security, per-tenant database strategies, OpenTelemetry, transport/hostel modules and statutory payroll/tax integrations.
