create extension if not exists pgcrypto;

create table if not exists technical_sheets (
    id uuid primary key default gen_random_uuid(),
    product_name text not null,
    brand text,
    category text,
    reference text,
    storage_path text not null unique,
    original_filename text not null,
    version_label text,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists technical_sheet_aliases (
    id uuid primary key default gen_random_uuid(),
    technical_sheet_id uuid not null references technical_sheets(id) on delete cascade,
    alias text not null,
    normalized_alias text not null,
    created_at timestamptz not null default now(),
    unique(technical_sheet_id, normalized_alias)
);

create index if not exists idx_technical_sheets_product_name
    on technical_sheets (lower(product_name));

create index if not exists idx_aliases_normalized
    on technical_sheet_aliases (normalized_alias);
