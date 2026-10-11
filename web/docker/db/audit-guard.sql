-- pg_restore 로 복원하면 기본 권한(ALTER DEFAULT PRIVILEGES)이 먼저 적용된 뒤 덤프의 GRANT 가 더해지기만 해서
-- 마이그레이션이 회수해 둔 권한이 사라질 수 있다. 복원 뒤 ytweb_owner 로 실행해 다시 회수하고 결과를 검사한다.
--  1) audit_log: UPDATE/DELETE/TRUNCATE (마이그레이션 0001, 감사 로그는 추가 전용)
--  2) alembic_version: INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER (마이그레이션 0002, 앱 계정은 구조 버전을 바꾸지 못한다, DEF-7-002)
-- 표가 아직 없는 덤프(아주 오래된 백업)는 건너뛴다. 여러 번 실행해도 결과가 같다.
DO $$
BEGIN
    IF to_regclass('public.audit_log') IS NOT NULL THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app;
        IF has_table_privilege('ytweb_app', 'public.audit_log', 'UPDATE')
           OR has_table_privilege('ytweb_app', 'public.audit_log', 'DELETE')
           OR has_table_privilege('ytweb_app', 'public.audit_log', 'TRUNCATE') THEN
            RAISE EXCEPTION 'audit_log 권한 회수에 실패했습니다.';
        END IF;
    END IF;

    IF to_regclass('public.alembic_version') IS NOT NULL THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.alembic_version FROM ytweb_app;
        IF has_table_privilege('ytweb_app', 'public.alembic_version', 'INSERT')
           OR has_table_privilege('ytweb_app', 'public.alembic_version', 'UPDATE')
           OR has_table_privilege('ytweb_app', 'public.alembic_version', 'DELETE')
           OR has_table_privilege('ytweb_app', 'public.alembic_version', 'TRUNCATE')
           OR has_table_privilege('ytweb_app', 'public.alembic_version', 'REFERENCES')
           OR has_table_privilege('ytweb_app', 'public.alembic_version', 'TRIGGER') THEN
            RAISE EXCEPTION 'alembic_version 권한 회수에 실패했습니다.';
        END IF;
        IF NOT has_table_privilege('ytweb_app', 'public.alembic_version', 'SELECT') THEN
            RAISE EXCEPTION 'alembic_version 읽기 권한이 사라졌습니다(앱이 버전을 읽지 못함).';
        END IF;
    END IF;
END
$$;
