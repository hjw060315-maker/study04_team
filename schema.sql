-- 팀 편성 앱의 테이블. Supabase SQL 편집기에서 실행한다. 모든 테이블 이름은 tf_로 시작한다.

create table if not exists tf_students (
    id            serial primary key,
    student_no    text not null unique,
    name          text not null,
    main_role     text check (main_role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text not null,
    is_admin      boolean not null default false
);

create table if not exists tf_student_sub_roles (
    student_id integer not null references tf_students(id) on delete cascade,
    role       text not null check (role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    primary key (student_id, role)
);

create table if not exists tf_teams (
    id   serial primary key,
    name text not null unique
);

-- (team_id, slot_no) 기본키와 student_id 유일 제약이 "마지막 자리에 두 명이 동시에 들어감"과
-- "한 학생은 한 팀에만 소속"을 DB에서 지킨다. slot_no 검사가 다섯 번째 자리를 막는다.
create table if not exists tf_members (
    team_id    integer not null references tf_teams(id) on delete cascade,
    slot_no    integer not null check (slot_no between 1 and 4),
    student_id integer not null unique references tf_students(id) on delete cascade,
    primary key (team_id, slot_no)
);

create table if not exists tf_applications (
    id         serial primary key,
    team_id    integer not null references tf_teams(id) on delete cascade,
    student_id integer not null references tf_students(id) on delete cascade,
    status     text not null check (status in ('대기', '승인', '거절')),
    reason     text,
    created_at timestamptz not null default now()
);

create table if not exists tf_votes (
    application_id integer not null references tf_applications(id) on delete cascade,
    voter_id       integer not null references tf_students(id) on delete cascade,
    vote           text not null check (vote in ('찬성', '거부')),
    primary key (application_id, voter_id)
);

create table if not exists tf_settings (
    key   text primary key,
    value text
);

-- AI 호출 기록. README의 실패 사례 근거로 쓴다.
create table if not exists tf_ai_logs (
    id          serial primary key,
    created_at  timestamptz not null default now(),
    attempt     integer not null,
    model       text not null,
    outcome     text not null,
    elapsed_sec real,
    detail      text
);
