-- Supabase PostgreSQL migration: first email-open vertical slice.
create table if not exists tracked_emails (
  id bigint generated always as identity primary key,
  user_id text not null check (char_length(user_id) <= 128),
  message_id text not null check (char_length(message_id) <= 512),
  sender_email text not null check (char_length(sender_email) <= 320),
  sender_name text not null check (char_length(sender_name) <= 320),
  subject text not null check (char_length(subject) <= 998),
  first_opened_at timestamptz not null,
  last_opened_at timestamptz not null,
  visit_count integer not null default 1 check (visit_count >= 1),
  email_risk_score integer not null check (email_risk_score between 0 and 100),
  risk_level text not null check (risk_level in ('low', 'medium', 'high')),
  score_source text not null check (score_source in ('mock-rule-based')),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique (user_id, message_id)
);

create table if not exists email_interactions (
  id bigint generated always as identity primary key,
  user_id text not null check (char_length(user_id) <= 128),
  message_id text not null check (char_length(message_id) <= 512),
  interaction_type text not null check (interaction_type in ('email_open')),
  event_timestamp timestamptz not null, metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists email_interactions_lookup_idx
  on email_interactions(user_id, message_id, interaction_type, event_timestamp desc);

comment on column tracked_emails.email_risk_score is
  'Temporary rule-based email score. Visit count is not an input and this is not an ML prediction.';
