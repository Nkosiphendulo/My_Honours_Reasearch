-- Schema for the campus co-design platform
create extension if not exists pgcrypto;

create table if not exists participants (
    participant_code text primary key,
    created_at timestamptz not null default now()
);

alter table participants enable row level security;
create policy participants_service_only on participants
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create table if not exists consent_records (
    id uuid primary key default gen_random_uuid(),
    participant_code text not null references participants(participant_code) on delete cascade,
    consented boolean not null,
    notes text,
    created_at timestamptz not null default now()
);

alter table consent_records enable row level security;
create policy consent_records_service_only on consent_records
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create table if not exists prompt_logs (
    id uuid primary key default gen_random_uuid(),
    participant_code text not null references participants(participant_code) on delete cascade,
    prompt_text text not null,
    response_text text not null,
    created_at timestamptz not null default now()
);

alter table prompt_logs enable row level security;
create policy prompt_logs_service_only on prompt_logs
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create table if not exists spc_records (
    id uuid primary key default gen_random_uuid(),
    participant_code text not null references participants(participant_code) on delete cascade,
    need_summary text not null,
    spc_json jsonb not null,
    created_at timestamptz not null default now()
);

alter table spc_records enable row level security;
create policy spc_records_service_only on spc_records
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create table if not exists rubric_scores (
    id uuid primary key default gen_random_uuid(),
    participant_code text not null references participants(participant_code) on delete cascade,
    scores jsonb not null,
    notes text,
    created_at timestamptz not null default now()
);

alter table rubric_scores enable row level security;
create policy rubric_scores_service_only on rubric_scores
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create table if not exists survey_responses (
    id uuid primary key default gen_random_uuid(),
    participant_code text not null references participants(participant_code) on delete cascade,
    responses jsonb not null,
    created_at timestamptz not null default now()
);

-- New table storing SPC outputs as structured fields with traced-from notes
create table if not exists spc_outputs (
    id uuid primary key default gen_random_uuid(),
    participant_code text not null references participants(participant_code) on delete cascade,
    overview text not null,
    overview_traced_from text,
    target_users text not null,
    target_users_traced_from text,
    functional_requirements jsonb not null,
    functional_requirements_traced_from text,
    nonfunctional_requirements jsonb not null,
    nonfunctional_requirements_traced_from text,
    assumptions_constraints text,
    assumptions_constraints_traced_from text,
    expected_benefits text,
    expected_benefits_traced_from text,
    created_at timestamptz not null default now()
);

alter table spc_outputs enable row level security;
create policy spc_outputs_service_only on spc_outputs
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

alter table survey_responses enable row level security;
create policy survey_responses_service_only on survey_responses
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');
