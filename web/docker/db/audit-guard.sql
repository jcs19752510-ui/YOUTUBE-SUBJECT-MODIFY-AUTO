-- pg_restore 로 복원하면 기본 권한(ALTER DEFAULT PRIVILEGES)이 먼저 적용된 뒤 덤프의 GRANT 가 더해지기만 해서
-- audit_log 의 UPDATE/DELETE/TRUNCATE 회수가 사라질 수 있다. 복원 뒤 ytweb_owner 로 실행해 다시 회수하고 결과를 검사한다.
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
END
$$;
